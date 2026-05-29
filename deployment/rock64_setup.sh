#!/bin/bash
set -e

# Rock64 Ubuntu setup for the Rock64 Robot host control stack.

sudo apt update
sudo apt install -y python3 python3-pip python3-opencv git


python3 -m pip install --upgrade pip
python3 -m pip install -r /home/$USER/Desktop/\Rock64\ Robot/ros2_ws/requirements.txt

sudo usermod -a -G dialout $USER

echo "Rock64 host control setup complete. Log out and log back in to apply dialout group changes."


root password: jokojoko
user account: rocky64
