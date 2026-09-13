#!/usr/bin/env bash
wait_deploy() {
  local ns="$1" name="$2" timeout="${3:-120s}"
  kubectl rollout status "deployment/${name}" -n "${ns}" --timeout="${timeout}" || return 1
}
