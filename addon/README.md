# Alexa+ add-on manifest (draft)

`addon.json` is drafted from the schema in Amazon's
[Alexa+ MCP Quickstart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html)
("addon.json schema reference"). Field names and nesting follow that page's example, and the values meet its
constraints: name ≤ 30 characters, short description ≤ 123, full description ≤ 4000, 3–4 example phrases,
all 6 light icon sizes, at least one 600×900 carousel image, and HTTPS URLs for privacy and terms. The
endpoint is the live MCP URL.

It's ready for `alexa-ai deploy` once Alexa+ onboarding is available to participants. The organizers
confirmed that the developer tools are partner-preview only (Devpost topic 45262). Before deploying:

- Replace every `https://REPLACE-ME.example.com/...` URL (privacy policy, terms of use, the 6 icons, the
  carousel image) with real hosted HTTPS PNG, JPG, or WEBP assets.
- `alexa-ai new mcp` scaffolds `addon-package/addon.json`. Copy this file there, or compare the generated one
  with it, because the CLI may have fields the docs page doesn't show.
- Auth isn't implemented (the DESIGN.md §6 spike didn't ship), and the Quickstart's addon.json has no auth fields, so there's nothing to configure here.
