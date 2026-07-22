# Echo Package 
## What is this?
This package allows you to send messages as your dex! Please don't send weird shi

## How to install
Run this eval

```py
.eval import base64, requests; code = base64.b64decode(requests.get("https://api.github.com/repos/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/contents/packages/admin/echo/installer.py?ref=v3").json()["content"]).decode(); wrapped = "async def __installer(bot, ctx):\n" + "\n".join("    " + l for l in code.splitlines()); globs = {"bot": bot, "ctx": ctx}; exec(wrapped, globs); await globs["__installer"](bot, ctx)
```
 Or just paste this in config/extra.toml
```toml
# Echo Package
[[ballsdex.packages]]
location = "git+https://github.com/GlitchedGlitch/BallsDex-Echo-Package.git@main"
path = "echo"
enabled = true
```
