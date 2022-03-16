#!/bin/bash
export GIT_USER="enter your git username here"


if [[ "$GIT_USER" == *enter* ]]; then
    echo "Please configure credential_helper.sh with your git username."
    exit 0
fi
git config --global credential.helper '!f() { sleep 1; echo "username='$GIT_USER'"; echo "password=${GIT_ACCESS_TOKEN}"; }; f'