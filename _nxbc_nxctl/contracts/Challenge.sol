// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ISetup {
    function chronicles(bytes32) external view returns (bool);
}

struct SoulFragment {
    address vessel;
    uint256 essence;
    bytes resonance;
}

contract Challenge {
    ISetup public setup;

    address public ascended;

    mapping(address => bool) public seekers;
    mapping(address => uint256) public seekerSince;

    mapping(address => uint256) public destinyPower;
    mapping(address => uint256) public soulEssence;
    mapping(address => uint256) public convergencePoints;

    mapping(bytes32 => bool) public consumed;

    uint256 public constant TRANSCENDENCE_ESSENCE = 1000 ether;
    uint256 public constant CONVERGENCE_REQUIREMENT = 100;

    event SeekerRegistered(address indexed seeker, uint256 timestamp);
    event DestinyOffered(address indexed seeker, uint256 power);
    event SoulsHarvested(address indexed seeker, uint256 essence);
    event ConvergenceAchieved(address indexed seeker, uint256 points);
    event Transcended(address indexed ascended);

    constructor(address setup_) {
        setup = ISetup(setup_);
    }

    function registerSeeker() external {
        require(!seekers[msg.sender], "Already a seeker");
        seekers[msg.sender] = true;
        seekerSince[msg.sender] = block.timestamp;
        emit SeekerRegistered(msg.sender, block.timestamp);
    }

    function offerDestiny(bytes calldata manifestation) external {
        require(seekers[msg.sender], "Not a seeker");

        bytes32 seal = keccak256(abi.encodePacked(msg.sender, manifestation));
        require(setup.chronicles(seal), "Manifestation not chronicled");
        require(!consumed[seal], "Chronicle already consumed");
        consumed[seal] = true;

        (bytes[] memory threads,, uint256[][] memory weights) =
            abi.decode(manifestation, (bytes[], bytes[], uint256[][]));

        uint256 power;
        for (uint256 i = 0; i < threads.length; i++) {
            power += threads[i].length * 1e15;
        }
        for (uint256 i = 0; i < weights.length; i++) {
            for (uint256 j = 0; j < weights[i].length; j++) {
                power += weights[i][j];
            }
        }

        destinyPower[msg.sender] += power;
        emit DestinyOffered(msg.sender, power);
    }

    function harvestSouls(bytes calldata agreement) external {
        require(seekers[msg.sender], "Not a seeker");

        bytes32 seal = keccak256(abi.encodePacked(msg.sender, agreement));
        require(setup.chronicles(seal), "Agreement not chronicled");
        require(!consumed[seal], "Chronicle already consumed");
        consumed[seal] = true;

        (SoulFragment[] memory fragments,,, address binder,) =
            abi.decode(agreement, (SoulFragment[], bytes32, uint32, address, address));

        require(binder == msg.sender, "Not the binder");

        uint256 essence;
        for (uint256 i = 0; i < fragments.length; i++) {
            essence += fragments[i].essence;
        }

        soulEssence[msg.sender] += essence;
        emit SoulsHarvested(msg.sender, essence);
    }

    function achieveConvergence(bytes calldata destinyData, bytes calldata soulData) external {
        require(seekers[msg.sender], "Not a seeker");

        bytes32 destinySeal = keccak256(abi.encodePacked(msg.sender, destinyData));
        bytes32 soulSeal = keccak256(abi.encodePacked(msg.sender, soulData));

        require(setup.chronicles(destinySeal), "Destiny not chronicled");
        require(setup.chronicles(soulSeal), "Soul pact not chronicled");
        require(!consumed[destinySeal], "Destiny already consumed");
        require(!consumed[soulSeal], "Soul pact already consumed");

        consumed[destinySeal] = true;
        consumed[soulSeal] = true;

        (bytes[] memory threads, bytes[] memory anchors,) =
            abi.decode(destinyData, (bytes[], bytes[], uint256[][]));

        (SoulFragment[] memory fragments,,, address binder,) =
            abi.decode(soulData, (SoulFragment[], bytes32, uint32, address, address));

        require(binder == msg.sender, "Not the binder");

        uint256 points = threads.length * anchors.length * fragments.length;
        convergencePoints[msg.sender] += points;

        emit ConvergenceAchieved(msg.sender, points);
    }

    function transcend(bytes calldata truth) external {
        require(seekers[msg.sender], "Not a seeker");
        require(ascended == address(0), "Another has already ascended");

        bytes32 seal = keccak256(abi.encodePacked(msg.sender, truth));
        require(setup.chronicles(seal), "Truth not chronicled");

        (SoulFragment[] memory fragments,,, address invoker, address witness) =
            abi.decode(truth, (SoulFragment[], bytes32, uint32, address, address));

        require(invoker == msg.sender, "You are not the invoker");

        uint256 totalEssence;
        for (uint256 i = 0; i < fragments.length; i++) {
            totalEssence += fragments[i].essence;
        }

        require(totalEssence >= TRANSCENDENCE_ESSENCE, "Insufficient essence in truth");
        require(witness == msg.sender, "The witness must be yourself");

        ascended = msg.sender;
        emit Transcended(msg.sender);
    }

    function getPowerLevels(address seeker) external view returns (
        uint256 destiny,
        uint256 soul,
        uint256 convergence
    ) {
        return (destinyPower[seeker], soulEssence[seeker], convergencePoints[seeker]);
    }
}
