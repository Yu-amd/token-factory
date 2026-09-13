#!/usr/bin/env bash
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
step() { echo -e "\n${BOLD}==> $*${NC}"; }
info() { echo -e "${CYAN}INFO:${NC} $*"; }
warn() { echo -e "${YELLOW}WARN:${NC} $*"; }
error() { echo -e "${RED}ERROR:${NC} $*" >&2; }
success() { echo -e "${GREEN}OK:${NC} $*"; }
