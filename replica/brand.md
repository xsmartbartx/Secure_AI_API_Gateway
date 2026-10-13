# Brand: NEXORA Gateway (2026-10-13)

## Name
Keep **NEXORA Gateway**. NEXORA is the parent platform (onenexora.com, live today) and Gateway is one of its products, so no rename and no similarity risk to a third party's mark from this work. Checks **not run**: US/EU/CA/WIPO trademark search for "NEXORA" in classes 9 and 42, app-store and handle search, domain registration records for onenexora.com. They are marked **to run** and need a trademark lawyer before paid launch. Nothing here claims the name is cleared.
Naming rule going forward: "NEXORA Gateway" in full on first mention, "Gateway" after. Never name competitors in marketing.

## Palette (original, replaces the placeholder blue)
Brand hue: deep teal. Chosen away from Azure/Apple-style blues (#0078d4 / #0071e3 / #007aff family) so the product does not read as a Microsoft or Apple lookalike. Roles unchanged in `replica/design/tokens.json`.
| role | light | dark |
| --- | --- | --- |
| accent | #0b6b63 | #4fd1c1 |
| accent-hover | #095850 | #7de3d6 |
| accent-subtle | #e0f2ef | #10302d |
| on-accent | #ffffff | #06201d |
Contrast: 0 AA failures in light and dark (accent on bg 6.37:1 light, 10.26:1 dark). Neutrals stay cool grey; danger/success/warning keep the semantic reds, greens and ambers.

## Logo brief
- **Idea:** a door that is open one notch: "one governed entry point". Gateway = threshold, not a lock.
- **Mark:** symbol + wordmark. Symbol: a rounded square with a single vertical slot / doorway cut, built from two geometric shapes. Wordmark: "NEXORA" in a medium-weight grotesque (Inter or Geist), "Gateway" lighter beside it (as in the header today).
- Works at 16px (favicon: symbol only, single colour) and 1024px.
- Deliverables: SVG (colour, mono, reversed), 1024x1024 app/icon PNG with no transparency, favicon set (16/32/48, SVG, apple-touch-icon), social image 1200x630.
- Must not resemble: Microsoft's four-square logo, Azure's "A" mark, Apple's apple, Kong/Portkey/LiteLLM marks. Put them next to drafts and check.
- Parent-brand fit: check against the existing NEXORA mark on onenexora.com before drawing; the Gateway symbol should sit beside it.

## Voice
Direct, not blunt. Plain, not casual. Candid, not apologetic. (Already the NEXORA tone: short declarative sentences, "what is real today".)
| do | don't |
| --- | --- |
| "Copy your new key now. You won't see it again." | "Please make sure to securely store your credentials!" |
| "No calls yet" + one action | "Oops! Nothing to see here 🎉" |
| "Not available yet. It is on the roadmap." | "Coming soon!!!" with no detail |
| "Monthly call quota reached. Upgrade your plan to continue." | "Error 429" |
| "We store a hash of each prompt, not the prompt." | "Enterprise-grade, military-grade security" |
Ten most-seen strings (all already written fresh in the app): hero "One governed door for every model call." / CTA "Open Gateway" / empty overview "No calls yet" / key reveal warning / quota error / "On the roadmap" stubs / playground empty "Your response will appear here." / billing "Online checkout is not enabled yet." / draft legal notice / pricing sub-line "Gateway pricing covers governance and logging."

## Sweep
`sweep.py` with `replica/brand.json`: clean. Remaining intentional mentions: Azure OpenAI, Azure Entra ID, Microsoft Sentinel as integrations in docs (nominative use). Font fallback stack reduced to `Inter, system-ui, sans-serif`. Eye check still to do: favicon (none yet), OG image (none yet), app icon (none).
Inspiration used, patterns only: Azure portal information architecture and density; Apple-style marketing restraint. No Microsoft/Apple logos, fonts, icons or copy.
