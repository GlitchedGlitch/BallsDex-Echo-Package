# Echo Package 
## What is this?
This package allows you to send messages as your dex! Please don't send weird shi

## How to install
Run this eval

```py
.eval import base64, requests; code = base64.b64decode(requests.get("https://api.github.com/repos/GlitchedGlitch/BallsDex-Echo-Package/contents/installer.py").json()["content"]).decode(); wrapped = "async def __installer(bot, ctx):\n" + "\n".join("    " + l for l in code.splitlines()); globs = {"bot": bot, "ctx": ctx}; exec(wrapped, globs); await globs["__installer"](bot, ctx)
```
 Or just paste this in config/extra.toml
```toml
# Echo Package
[[ballsdex.packages]]
location = "git+https://github.com/GlitchedGlitch/BallsDex-Echo-Package.git@1.0.0#main"
path = "echo"
enabled = true
```
