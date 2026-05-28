#!/bin/bash

echo "UID=$(id -u)" > .env
echo "GID=$(id -g)" >> .env
echo "PWD=$(pwd)" >> .env