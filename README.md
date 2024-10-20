# Image generator

Run with:
```
uv run base-img.py
```

## AppArmor and other user namespace restrictions

The image generator makes use of user namespaces to please Nix's absolute paths.
In case you see an error related to *"unprivileged user namespaces"* being either
*"disabled in kernel"* or *"restricted by AppArmor"*, please refer to the
[AppArmor wiki](https://gitlab.com/apparmor/apparmor/-/wikis/unprivileged_userns_restriction)
on the subject.
