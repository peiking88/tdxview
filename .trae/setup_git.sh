#!/bin/bash

# Git configuration for tdxview project
echo "Setting up Git configuration for tdxview..."

# Configure GitHub domain replacement
git config url."https://bgithub.xyz/".insteadOf "https://github.com/"

# Disable SSL verification for pushes
git config http.sslVerify false

# Configure username
git config user.name "peiking88"

echo "Git configuration completed."
echo "GitHub domain: bgithub.xyz"
echo "SSL verification: disabled"
echo "Username: peiking88"
echo ""
echo "Note: GitHub authentication token should be set via environment variable GITHUB_TOKEN"
echo "or configured in your system's credential manager."