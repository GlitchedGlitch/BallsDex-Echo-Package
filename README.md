# Echo Package 
## What is this?
This package allows you to send messages as your dex! Please don't send weird shi

## How to install
Add this to config/extra.toml (or create the file if it doesn't exist)
```toml
# Echo Package
[[ballsdex.packages]]
location = "git+https://github.com/GlitchedGlitch/BallsDex-Echo-Package.git@2.1.0"
path = "echo"
enabled = true
```

## Features
This package has a lot of features!!!
| Feature | Description |
|---------|-------------|
|Message|Send a custom text message (duh)|
|File|Add a custom file (image, video, audio, basically any file uploadable to discord!)|
|Style|Choose between embed or container, basically wrap around your custom text a message style!|
|Channel|Choose a custom channel to send the message, works with links and channel ids (even outside the server!)|
|DM|Send the message in someone's dms instead|
|Reply|Put a message link so make the message reply to an user|
|edit_message|Edit a message sent by the bot instead|
|delete_message|Delete a given message instead of sending|
|Mention|If mentions should be on|
|Preview|Preview your message before sending|

There are also special qol characters to make your life easier!

There are also special QoL characters to make your life easier!

| Character | Description |
|-----------|-------------|
| {e:Ball Full Name} | Send a ball emoji if available |
| {s:line} | Create a separator line when using Container style |
| {c:model} | Show the number of objects for a model |
| {c:model:filter} | Show the number of objects matching a specific filter |
| {t:D/M/Y H:M:S} | Convert a date/time into a Discord timestamp |
| {t:D/M/Y H:M:S:type} | Convert a date/time into a Discord timestamp with a specific display format |

|List of available models|
|------------------------|
|economies|
|regimes|
|groups|
|balls|
|ballinstances|
|guildconfigs|
|players|
|specials|
|guilds|
|specialinstances|

For timestamp formats you can see [this](https://gist.github.com/LeviSnoot/d9147767abeef2f770e9ddcd91eb85aa) page. They're the last letters in the timestamp btw!