Add a new page to the Seeco Figma file called "Page 10 — Watchlist".
This page is part of the investor and conscious consumer workflow. 
It should match Seeco's existing design language: 
soft cream or white background, green and blue palette, rounded cards, 
subtle shadows, generous whitespace, and flat vector icons.

Do NOT change any other page.
Build this as a full production-ready design with realistic content, 
all states, all modals, and all interactions documented.

─────────────────────────────────────────────
STEP 1 — EMAIL GATE MODAL (First-time entry)
─────────────────────────────────────────────

Design a centered modal overlay that appears the first time any user 
visits the Watchlist page, before any content is shown.

The overlay background should be a soft dark blur 
(semi-transparent dark green tint over the page) to hint that the 
watchlist content exists behind it.

Modal card specs:
- Centered on screen, max width 480px
- Rounded corners (radius 20px)
- Soft white background
- Seeco logo or wordmark at the top
- Subtle leaf or nature icon above the title
- Headline text: "Unlock your Seeco Watchlist"
- Supporting copy (one line): 
  "Enter your email to access and manage your personalised 
  biodiversity watchlist — free and no password required."

Form inside the modal:
- Email input field, full width
  - Placeholder: "your@email.com"
  - Validation inline below field:
    - Empty submit attempt: "Please enter a valid email address."
    - Invalid format: "That doesn't look like a valid email — 
      double check and try again."
    - Already verified: "Welcome back — loading your watchlist..."
- Primary green CTA button: "Send verification link"
- Helper text beneath button: 
  "We'll email you a one-click verification link. 
  No password needed."
- Below that: a subtle text link — "Why do we need your email?"
  (clicking expands an inline accordion with 2 short lines explaining 
  that Seeco uses email to save your watchlist across devices and 
  send alerts when your watched companies change)

Modal states to design:
1. Default state: empty email field, button enabled
2. Typing state: email field active with outline highlight
3. Loading state: button shows spinner, field disabled, 
   text changes to "Sending link..."
4. Sent state: 
   - Email input area replaced with a green success banner
   - Icon: envelope with checkmark
   - Text: "Check your inbox — we've sent a link to 
     your@email.com"
   - Subtext: "Didn't get it? Check spam or 
     [Resend link] after 60 seconds."
   - Countdown timer chip: "Resend in 0:47"
5. Verified state (after clicking the link — simulated): 
   - Brief animated success confirmation
   - Green check icon
   - Text: "You're verified — welcome to your watchlist!"
   - Auto-dismiss after 2 seconds and reveal the full page

─────────────────────────────────────────────
STEP 2 — MAIN WATCHLIST PAGE LAYOUT
─────────────────────────────────────────────

After email verification, show the full Watchlist page.
Use Seeco's standard desktop layout:
- Left sidebar: navigation (same style as all other pages)
- Top bar: search, notifications bell, user avatar with verified 
  email badge showing a green tick + truncated email address
- Main content area: split into two zones:
  - Left zone (65% width): Watchlist table and controls
  - Right zone (35% width): Selected company side card panel

Page header:
- Page title: "My Watchlist"
- Subtitle: "Track biodiversity risk changes across your 
  saved companies"
- Small meta line: "Watching 6 companies · 2 alerts active · 
  Last refreshed 3 mins ago"
- Right side of header: two action buttons
  - Primary button: "+ Add company" (green)
  - Secondary ghost button: "Manage alerts"

─────────────────────────────────────────────
STEP 3 — WATCHLIST TABLE / LIST AREA
─────────────────────────────────────────────

Design a clean, scannable watchlist table showing saved companies.
This is not a dense spreadsheet — it should feel like a modern 
investor card-list hybrid.

Show each watchlist entry as a horizontal row card with:
- Company logo placeholder (rounded square icon, 36px)
- Company name (semibold)
- Industry tag chip (e.g. "Mining & Resources", "Food Manufacturing")
- ABN (light grey, small)
- Biodiversity Risk Score badge:
  - Large score number (e.g. 74)
  - Risk level label: Low / Medium / High
  - Color coded: green / yellow / red
- 7-day score change indicator:
  - Up arrow + "+5" in red if risk increased
  - Down arrow + "-3" in green if risk decreased
  - Dash if stable
- Confidence level small chip (e.g. "91% confident")
- Last updated timestamp (light grey, e.g. "Updated 2h ago")
- Active alerts badge:
  - If alerts exist: orange pill with alert count 
    (e.g. "2 alerts")
  - If none: empty (no badge shown)
- Row-end actions (shown on hover):
  - Bell icon: toggle alerts on/off
  - Pencil icon: edit label or notes
  - Trash icon: remove from watchlist
  - Three-dot overflow menu

Show 6 sample companies in the table with realistic Australian 
company names, e.g.:
  1. BHP Group Limited — Mining, score 78, High, +6 change, 2 alerts
  2. Woolworths Group — Food Retail, score 42, Medium, -2 change
  3. Origin Energy — Energy, score 65, Medium, +1 change, 1 alert
  4. Treasury Wine Estates — Agriculture, score 31, Low, -4 change
  5. Fortescue Ltd — Mining, score 82, High, +8 change, 3 alerts
  6. Bega Cheese Limited — Food Mfg, score 28, Low, 0 change

Selected row state:
- Highlighted with a soft left green border (4px) and 
  light green-tinted background
- All other rows return to white background

Table toolbar above the rows:
- Left: search input "Search your watchlist..."
- Left: Filter chips row — All, High Risk, Medium Risk, 
  Low Risk, Alerts Active, Recently Updated
- Right: Sort dropdown — "Sort by: Risk score (high to low)"
- Right: View toggle — list view icon / card grid icon

─────────────────────────────────────────────
STEP 4 — RIGHT-SIDE COMPANY SUMMARY CARD
─────────────────────────────────────────────

When a user clicks any company row, a side panel opens on the right 
(35% width, full page height, sticky). This panel should NOT be a 
modal — it slides in from the right and lives beside the table.

Side card panel specs:
- Soft white card background
- Left edge has a subtle green border line
- Top: close/collapse icon (X) top right
- Scrollable content inside

Side card contents (top to bottom):

1. Company identity block:
   - Logo (placeholder)
   - Company name (H3, semibold)
   - Legal name + ABN in small grey text
   - Industry chip
   - HQ location with map pin icon
   - Market status pill: Public / Private
   
2. Biodiversity risk hero block:
   - Large risk score (e.g. 78 / 100) in bold
   - Risk level badge: High (red)
   - 7-day change: "+6 this week" with upward arrow in red
   - Confidence chip: "88% confidence"
   - Short helper text:
     "Score of 78 reflects elevated biodiversity risk 
     based on spatial overlap, supplier exposure, and 
     recent regulatory signals."

3. Score composition mini bar:
   - Small horizontal segmented bar showing score breakdown:
     - Direct operations (22 pts)
     - Supply chain (18 pts)
     - Protected area proximity (15 pts)
     - Controversy signals (14 pts)
     - Disclosure gap (9 pts)
   - Each segment colored appropriately

4. Plain English summary:
   - 3 bullet points summarising the company's current risk:
     - e.g. "Operations near 4 EPBC-listed sensitive areas"
     - e.g. "Tier-1 supplier linked to land-clearing event in QLD"
     - e.g. "ASX filing noted TNFD alignment underway but incomplete"

5. Divider line

6. Recent updates feed (most important section):
   Label: "Recent Updates" with a small green dot 
   (indicating live data)
   Show a chronological activity feed with 5–7 updates:
   
   Each update item contains:
   - Event type icon:
     - Warning triangle (orange) for risk increase
     - Shield check (green) for positive signal
     - Document icon for new evidence
     - Bell icon for alert triggered
     - Trend arrow for score change
   - Event headline (short, 1 line max)
   - Source label (small grey text, e.g. "ABC News", 
     "ASX Announcement", "EPBC Database", "Supply chain signal")
   - Timestamp (e.g. "2 hours ago", "Yesterday", "3 days ago")
   - Optional: tiny confidence chip where relevant

   Sample updates to show:
   - "Risk score increased from 72 to 78 — new evidence added" 
     · 2h ago
   - "New ASX filing mentions environmental compliance review" 
     · Yesterday · ASX
   - "Tier-1 supplier Greenfield Farms flagged for land clearing" 
     · 2 days ago · Supply chain signal
   - "EPBC database updated — 1 new protected area overlap confirmed" 
     · 3 days ago · Gov data
   - "Alert triggered: score moved +6 in 7 days — above threshold" 
     · 4 days ago · Alert engine
   - "News article flagged: habitat risk near WA mining site" 
     · 5 days ago · Media

7. Divider line

8. Action buttons at the bottom of the side card:
   - Primary: "View full company report →" (green, full width)
   - Secondary: "Compare with peers" (ghost, full width)
   - Tertiary text link: "Remove from watchlist" (red text, small)

─────────────────────────────────────────────
STEP 5 — ADD COMPANY MODAL
─────────────────────────────────────────────

Design a modal for when the user clicks "+ Add company".

Modal: centered, max width 560px, rounded corners.
Title: "Add a company to your watchlist"
Subtitle: "Search by company name, brand, or ABN"

Inside the modal:

Search input (large, full width):
- Placeholder: "e.g. BHP, Tim Tams, 12 345 678 901"
- Real-time search results appear below as a dropdown list
- Each result row shows:
  - Company logo placeholder
  - Company name
  - ABN
  - Industry chip
  - Risk score badge (color coded)
  - "Already watching" chip if already in list

Below the search results, after selecting a company:
- Selected company card appears with logo, name, ABN, 
  industry, and current risk score
- Optional notes field: "Add a private label or note 
  (optional)" — placeholder: "e.g. Portfolio holding, 
  supplier review"
- Alert preference section:
  - Toggle: "Notify me when risk score changes significantly"
  - Sub-option (visible when toggle on): 
    "Alert me when score changes by:" 
    with dropdown: ±5 pts / ±10 pts / any change
  - Toggle: "Send me a weekly summary email"

Footer of modal:
- Primary button: "Add to watchlist" (green, full width)
- Cancel text link beneath

States to design:
- Empty search state
- Typing/results state
- Company selected state
- Already watching error state:
  - Inline yellow banner: "BHP Group is already in your watchlist."
- Success confirmation (brief, then auto-dismiss):
  - Green checkmark
  - "BHP Group added to your watchlist"
  - "You'll be notified when their biodiversity risk changes."

─────────────────────────────────────────────
STEP 6 — EDIT