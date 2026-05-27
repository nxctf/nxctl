// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./Setup.sol";

contract ChallengeFactory {
    address public immutable owner;
    mapping(address => Setup) public setupOf;

    event Spawned(address indexed player, address indexed setup);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function spawn() external returns (address) {
        return _spawn(msg.sender);
    }

    function spawnFor(address player) external onlyOwner returns (address) {
        return _spawn(player);
    }

    function _spawn(address player) internal returns (address) {
        require(player != address(0), "invalid player");
        require(address(setupOf[player]) == address(0), "already spawned");

        Setup setup = new Setup(player);
        setupOf[player] = setup;

        emit Spawned(player, address(setup));
        return address(setup);
    }

    function isSolved(address player) external view returns (bool) {
        Setup setup = setupOf[player];
        if (address(setup) == address(0)) {
            return false;
        }
        return setup.isSolved();
    }
}
