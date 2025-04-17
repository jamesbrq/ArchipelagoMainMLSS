# Setup Guide for Paper Mario The Thousand Year Door Archipelago

## Required Software

- Dolphin Emulator: [Dolphin Emulator Releases](https://dolphin-emu.org/download/?ref=btn)
- Archipelago: [Latest releases](https://github.com/ArchipelagoMW/Archipelago/releases)
- A US copy of Paper Mario The Thousand Year Door. (EU and JP versions are not supported at this time)

## Installing the APWorld

Place the apworld in the `custom_worlds` folder of your Archipelago installation. Please also check the latest release for the `lib.zip` file,
place the contents of the `lib` folder in the zip into the `lib` folder in your archipelago installation. This is required for the world to work.

## Configuring your YAML file

### What is a YAML file and why do I need one?

Your YAML file contains a set of configuration options which provide the generator with information about how it should
generate your game. Each player of a multiworld will provide their own YAML file. This setup allows each player to enjoy
an experience customized for their taste, and different players in the same multiworld can all have different options.

### Where do I get a YAML file?

You can customize your options by visiting the 
[Paper Mario The Thousand Year Door Options Page](/games/Paper%20Mario%20The%20Thousand%20Year%20Door/player-options)

## Joining a MultiWorld Game

### Obtain your GC patch file

When you join a multiworld game, you will be asked to provide your YAML file to whoever is hosting. Once that is done,
the host will provide you with either a link to download your data file, or with a zip file containing everyone's data
files. Your data file should have a `.apttyd` extension.

Double-click on your `.apttyd` file to start your client and start the ROM patch process. Once the process is finished, the client and the emulator will be started automatically.

### Connect to the Multiserver

To connect the client to the multiserver simply put `<address>:<port>` on the textfield on top and press enter (if the
server uses password, type in the bottom textfield `/connect <address>:<port> [password]`)
