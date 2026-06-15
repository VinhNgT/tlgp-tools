## UI Control Type Classification Guide

### Control Types

| Type | Visual Indicators | Common Examples |
|---|---|---|
| `Button` | Rounded rectangle with text, solid or outlined fill, tap target | "Mua ngay", "Thêm vào giỏ", back arrow button |
| `Text` | Static label or paragraph, no interactive affordance | Titles, prices, descriptions, timestamps |
| `Icon` | Small graphical symbol, typically ≤32px, no text | Heart, share, arrow, cart, menu dots (⋮) |
| `Image` | Photo area, banner, product image, avatar, logo | Product photos, promotional banners, user avatars |
| `Component` | A nested group containing multiple sub-elements | A card with image+text+button, a header bar |
| `Tabbar` | Horizontal tab-style selector with multiple options | Category tabs, filter tabs |
| `Slide` | Dot indicators or carousel controls | Image carousel dots, page indicators |
| `TextField` | Input field with border/underline, placeholder text | Search bars, form inputs |
| `Checkbox` | Square toggle control, checked/unchecked state | Agreement checkboxes, multi-select options |
| `Switch` | Toggle slider control, on/off state | Settings toggles, feature flags |

### Classification Rules

1. If the element contains multiple distinct sub-elements → `Component`
2. If it's interactive and looks tappable → `Button` (unless it's an icon)
3. If it's a small symbol without text → `Icon`
4. If it's a photo or illustration area → `Image`
5. If it's text content without interactivity → `Text`
6. If it accepts user input → `TextField`
7. When in doubt between Button and Icon: if it has text, it's a Button

### Interaction Inference

| Control Type | Typical Interactions |
|---|---|
| `Button` | Navigate to screen, open bottom sheet, call API, submit form |
| `Icon` | Toggle state (favorite), share content, navigate, open menu |
| `Image` | Open image viewer, navigate to detail screen |
| `Component` | Scroll content, expand/collapse, navigate |
| `TextField` | Show keyboard, filter results, validate input |
| `Tabbar` | Switch displayed content category |
| `Checkbox` / `Switch` | Toggle boolean state, update preferences |
