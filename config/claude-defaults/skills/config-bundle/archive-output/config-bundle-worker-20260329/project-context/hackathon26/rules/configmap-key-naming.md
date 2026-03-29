# ConfigMap Key Naming

When updating K8s ConfigMaps with `kubectl create configmap --from-file`, the key name becomes the filename in the mount.

- `--from-file=worker.py=local-file.py` mounts as `/mount-path/worker.py`
- `--from-file=local-file.py` mounts as `/mount-path/local-file.py`

Always match the key name to what the deployment command expects (check `containers[].command` in the deployment spec).
