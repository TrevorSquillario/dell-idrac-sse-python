# Release

```
git commit -m 'Release 2.3.1'
git checkout main
git merge devel

# Only tag releases as this triggers a git workflow (.github/workflows/docker-build-and-push.yaml) 
git tag v2.3.1
git push origin v2.3.1
git push origin main
```