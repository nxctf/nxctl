import hashlib
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from nxbcl.launcher.config import NXBCLConfig
import nxbcl.launcher.app as launcher_app
from nxbcl.launcher.db.connection import init_db
from nxbcl.launcher.pow.service import PowService
from nxbcl.launcher.auth.session import SessionService

def solve_pow(salt: str, zero_prefix: str) -> str:
    nonce = 0
    while True:
        solution = str(nonce)
        h = hashlib.sha256()
        h.update((salt + solution).encode("utf-8"))
        if h.hexdigest().startswith(zero_prefix):
            return solution
        nonce += 1

@pytest.fixture
def temp_nxbcl_env():
    """Fixture to set up a temporary environment for NXBCL tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_file = tmp_path / "nxbcl.db"

        # Initialize schema
        init_db(db_file)

        # Create a mock config object
        test_cfg = NXBCLConfig()
        test_cfg.data_dir = str(tmp_path)
        # Override paths
        test_cfg.__class__.db_file = property(lambda self: db_file)
        test_cfg.__class__.data_path = property(lambda self: tmp_path)
        test_cfg.__class__.chall_dir = property(lambda self: tmp_path / "chall")
        test_cfg.__class__.locks_dir = property(lambda self: tmp_path / "locks")
        test_cfg.pow_zero_prefix = "00"  # Easy prefix for tests
        test_cfg.session_ttl_seconds = 3600
        test_cfg.instance_ttl_seconds = 600
        test_cfg.max_concurrent = 2

        # Monkeypatch the app's config
        old_config = launcher_app.config
        launcher_app.config = test_cfg

        yield test_cfg

        launcher_app.config = old_config

def test_pow_and_session_services(temp_nxbcl_env):
    cfg = temp_nxbcl_env
    pow_service = PowService(cfg.db_file, cfg.pow_zero_prefix, 60)
    session_service = SessionService(cfg.db_file, cfg.session_ttl_seconds)

    user_id = "test-user"
    challenge_id = "04-convergence"

    # 1. Issue PoW challenge
    chal = pow_service.issue_challenge(user_id, challenge_id)
    assert "challenge_token" in chal
    assert "salt" in chal
    assert chal["zero_prefix"] == cfg.pow_zero_prefix

    # 2. Solve PoW
    sol = solve_pow(chal["salt"], chal["zero_prefix"])

    # 3. Verify Solution (first attempt should succeed)
    verified = pow_service.verify_solution(user_id, challenge_id, chal["challenge_token"], sol)
    assert verified is True

    # 4. Verify Solution again (second attempt should fail - single use token)
    verified_again = pow_service.verify_solution(user_id, challenge_id, chal["challenge_token"], sol)
    assert verified_again is False

    # 5. Create session
    session_id = session_service.create_session(user_id, challenge_id)
    assert len(session_id) == 64

    # 6. Validate session
    session_data = session_service.validate_session(session_id, challenge_id)
    assert session_data is not None
    assert session_data["user_id"] == user_id
    assert session_data["challenge_id"] == challenge_id

    # 7. Validate incorrect challenge session
    assert session_service.validate_session(session_id, "wrong-challenge") is None

def test_api_endpoints_flow(temp_nxbcl_env):
    client = TestClient(launcher_app.app)
    cfg = temp_nxbcl_env

    user_id = "api-user-1"
    challenge_id = "04-convergence"

    # Pre-create the challenge in registry fallback so registry finds it
    fallback_chall_dir = Path(__file__).resolve().parent.parent / "challenges" / challenge_id
    fallback_chall_dir.mkdir(parents=True, exist_ok=True)
    with open(fallback_chall_dir / "challenge.yml", "w") as f:
        f.write(f"id: {challenge_id}\nname: Convergence Challenge\nrpc_internal: http://anvil:8545\n")

    # A. Issue PoW via API
    res = client.post(
        f"/api/challenges/{challenge_id}/pow/challenge",
        json={"user_id": user_id},
        headers={"X-User-Id": user_id}
    )
    assert res.status_code == 200
    chal = res.json()
    token = chal["challenge_token"]
    salt = chal["salt"]

    # B. Solve PoW
    sol = solve_pow(salt, cfg.pow_zero_prefix)

    # C. Submit solution
    res = client.post(
        f"/api/challenges/{challenge_id}/pow/solution",
        json={
            "challenge_token": token,
            "solution": sol,
            "user_id": user_id
        }
    )
    assert res.status_code == 200
    sol_resp = res.json()
    assert sol_resp["status"] == "success"
    session_id = sol_resp["session_id"]

    # D. Start instance (without cookies/headers -> should fail)
    client.cookies.clear()
    res = client.post(f"/api/challenges/{challenge_id}/start")
    assert res.status_code == 401


    # E. Start instance (with cookies -> should succeed)
    client.cookies.set("nxbc_session", session_id)
    res = client.post(
        f"/api/challenges/{challenge_id}/start",
        headers={"X-User-Id": user_id}
    )
    assert res.status_code == 200
    inst = res.json()
    assert inst["status"] == "running"
    assert inst["chain_id"] == 31337
    assert inst["rpc_url"] == "http://localhost:8545"
    assert inst["setup_address"] == inst["deploy_address"]
    instance_id = inst["instance_id"]
    wallet_address = inst["wallet_address"]

    # F. Idempotent call to start should return SAME instance
    res = client.post(
        f"/api/challenges/{challenge_id}/start",
        headers={"X-User-Id": user_id}
    )
    assert res.status_code == 200
    inst2 = res.json()
    assert inst2["instance_id"] == instance_id
    assert inst2["wallet_address"] == wallet_address

    # G. Restart instance (should create NEW instance and wallet)
    res = client.post(
        f"/api/challenges/{challenge_id}/restart",
        headers={"X-User-Id": user_id}
    )
    assert res.status_code == 200
    inst_re = res.json()
    assert inst_re["instance_id"] != instance_id
    assert inst_re["wallet_address"] != wallet_address
    assert inst_re["status"] == "running"
