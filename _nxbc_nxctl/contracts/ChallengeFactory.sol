// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./Setup.sol";

contract ChallengeFactory {
    mapping(address => Setup) public setupOf;

    event Spawned(address indexed player, address indexed setup);

    function spawn() external returns (address) {
        require(address(setupOf[msg.sender]) == address(0), "already spawned");

        Setup setup = new Setup();
        setupOf[msg.sender] = setup;

        emit Spawned(msg.sender, address(setup));
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
