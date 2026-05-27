// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./Challenge.sol";

contract Setup {
    address public immutable player;
    Challenge public challenge;
    mapping(bytes32 => bool) public chronicles;

    constructor(address player_) {
        require(player_ != address(0), "invalid player");
        player = player_;
        challenge = new Challenge(address(this), player_);
    }

    modifier onlyPlayer() {
        require(msg.sender == player, "not player");
        _;
    }

    function sealDestiny(bytes calldata manifestation) external onlyPlayer {
        (bytes[] memory threads, bytes[] memory anchors, uint256[][] memory weights) =
            abi.decode(manifestation, (bytes[], bytes[], uint256[][]));

        require(threads.length >= 1, "Destiny requires threads");
        require(anchors.length >= 1, "Destiny requires anchors");
        require(weights.length >= 1, "Destiny requires weights");

        for (uint256 i = 0; i < threads.length; i++) {
            require(threads[i].length > 0, "Empty thread detected");
        }

        for (uint256 i = 0; i < anchors.length; i++) {
            require(anchors[i].length > 0, "Empty anchor detected");
        }

        for (uint256 i = 0; i < weights.length; i++) {
            require(weights[i].length > 0, "Empty weight array detected");
        }

        bytes32 seal = keccak256(abi.encodePacked(msg.sender, manifestation));
        require(!chronicles[seal], "Already chronicled");
        chronicles[seal] = true;
    }

    function bindPact(bytes calldata agreement) external onlyPlayer {
        (SoulFragment[] memory fragments,,, address binder, address witness) =
            abi.decode(agreement, (SoulFragment[], bytes32, uint32, address, address));

        require(fragments.length >= 1, "Pact requires soul fragments");
        require(binder != address(0), "Invalid binder");
        require(witness != address(0), "Invalid witness");

        for (uint256 i = 0; i < fragments.length; i++) {
            require(fragments[i].vessel != address(0), "Invalid vessel in fragment");
            require(fragments[i].essence <= 100 ether, "Essence too powerful for pact");
        }

        bytes32 seal = keccak256(abi.encodePacked(msg.sender, agreement));
        require(!chronicles[seal], "Already chronicled");
        chronicles[seal] = true;
    }

    function isSolved() external view returns (bool) {
        return challenge.ascended() == player;
    }
}
