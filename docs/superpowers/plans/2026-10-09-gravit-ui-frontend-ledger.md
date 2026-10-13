# SDD ledger — plan: docs/superpowers/plans/2026-10-09-gravit-ui-frontend.md
Setup: worktree .claude/worktrees/gravit-ui on feat/gravit-ui from local main 69225d8; spec docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md read as the authority.
Setup: Ruling: spec and plan were untracked in the primary checkout; copied into the branch and committed as its first commit — they travel with the work — cost if wrong: one docs commit to drop; the primary copies stay untracked and must be removed before merging the branch into main.
Task 1: Ruling: the plan test script node --test tests/ fails on Node 22, which treats a bare directory as a module — changed to node --test tests/*.test.js, shell-expanded so it also runs on Node 20; every later step that says node --test tests/ runs npm test instead — cost if wrong: none, one script line.
Task 1: complete (commits eb0f20e..3aa6793, tests: npm test → # duration_ms 143.186916)
Task 2: complete (commits 3aa6793..c1f9e8f, tests: npm test → # duration_ms 135.031916)
Task 2+: Ruling: the background security review of the Task 1 commit found two real defects in serve.js, a malformed percent-escape threw in the async handler and hung the request, and a raw /.//css target redirected to //css/ — fixed test-first with two new serve tests RED then GREEN, commit 5517532 — cost if wrong: none, both are guards on a local dev server.
Task 3: complete (commits 5517532..fac3aae, tests: npm test → # duration_ms 144.9895)
Task 4: complete (commits fac3aae..d735fe4, tests: npm test → # duration_ms 101.782833)
Task 5: complete (commits d735fe4..3cd6117, tests: npm test → # duration_ms 104.205417)
Task 6: complete (commits 3cd6117..993ca91, tests: npm test → # duration_ms 138.784625)
Task 7: complete (commits 993ca91..81b9650, tests: npm test → # duration_ms 134.036625)
Task 8: complete (commits 81b9650..c9c5e35, tests: npm test → # duration_ms 148.995291)
Task 9: complete (commits c9c5e35..c867b32, tests: npm test → # duration_ms 151.481875)
Task 10: complete (commits c867b32..588db92, tests: npm test → # duration_ms 167.018375)
Task 11: complete (commits 588db92..fc98075, tests: npm test → # duration_ms 165.298916)
Task 12: Ruling: the plan test expected main class "main with-drawer" but renderAccount emits "main acct with-drawer" and Task 13 styles .acct — corrected the test regex to the emitted class list — cost if wrong: none, the class is what the stylesheet needs.
Task 12: Ruling: the plan test pins the switch attributes as role, aria-checked, data-action, data-key while the code put aria-label between them — moved aria-label to the end in the code so the test stands as written — cost if wrong: none, attribute order has no effect.
Task 12: complete (commits fc98075..d0a9ab4, tests: npm test → # duration_ms 166.612)
Task 13: complete (commits d0a9ab4..5e2d44c, tests: npm test → # duration_ms 140.380958)
Pre-flight: a 14-agent scan, run in the background while Tasks 1-13 were built, confirmed 38 findings after adversarial verification, many duplicated across groups. Three were already handled in Tasks 1 and 12. The rest are ruled below and fixed before Task 14, so app.js is written once against the final interfaces.
Pre-flight: Ruling: --blue collides with Linqi's own --blue, which is his orange RWA colour, and spec 3.4 allows one new token — app.css uses his --alloc-equity for the equity blue; the white words on it keep a token renamed --on-equity, the only way to stay hex-free in Black where --on-primary is dark — cost if wrong: spec 3.4 should list --on-equity as a second addition, the operator's call.
Pre-flight: Ruling: createStore read localStorage itself and skipped the version check in initialState, so a stale save would boot — createStore takes an accept predicate and boot passes the version check — cost if wrong: none.
Pre-flight: Ruling: a route naming a missing conversation stayed in state, so the rail showed no current row and send opened a new conversation instead of writing into the one on screen — nav and send normalise to the first conversation, boot and hashchange rewrite the hash — cost if wrong: none, Review Focus 3.
Pre-flight: Ruling: spec 6 kinds 13 and 14 — breaking news is a banner for 5 s then a red-edged message, and a declined call becomes a message — dismissBanner writes the breaking message, the director auto-dismisses after 5 s, answerCall writes a call card — cost if wrong: two extra messages per demo beat.
Pre-flight: Ruling: spec 7.3 says pressing Installed offers uninstall by showing the trash key, not a native confirm — added askUninstall state — cost if wrong: one reducer and one key state.
Pre-flight: Ruling: spec 7.7 lists an icon field with a 44 px slot and initials by default in the upload drawer — added it — cost if wrong: one form row.
Pre-flight: Ruling: spec 10 forbids explanatory small print — removed the stub line Linqi 的页面, the publish toast explanations, and the no-recycle-bin sentence in the Forget all confirm — cost if wrong: copy only.
Pre-flight: Ruling: replies scheduled before Stop Gravit or Withdraw still landed — append drops non-owner messages into a stopped or withdrawn conversation — cost if wrong: none.
Pre-flight: Ruling: driver defects — the BTC regex matched something and method, a grant asked to install News sentiment even when installed, and every receipt reused ord-0001 and ledger 41 — word boundaries, ctx.installed, and ord and ledger placeholders filled from the state counters in append — cost if wrong: none.
Pre-flight: Ruling: group previews prefixed system lines with a bare colon; Open in Messages inside a card also opened the card drawer; the banner link was preventDefaulted and never navigated; card divs with role button ignored Enter and Space; reset kept the old theme — each fixed where it lives — cost if wrong: none.
Pre-flight: Ruling: every re-render replaced the inputs, which broke Chinese IME composition in the title and search inputs and dropped text typed into Memory and the upload form — the input handler skips composing events and dispatches on compositionend, and render keeps the values of inputs with ids — cost if wrong: none.
Pre-flight: Ruling: the css test built the upload, installed and search states without navigating to Discover, so their classes were never checked — wrapped them in nav to discover; a layout check in the browser covers the drawer and toast placement findings — cost if wrong: none.
Task 14: Ruling: the wiring rulings of the pre-flight need tests, so app.js exports four helpers boot now uses, makeStore, settle, showBreaking and answerFlow, each with an app test that failed first — cost if wrong: four extra exports on app.js.
Task 14: complete (commits 5e2d44c..097a3ca, tests: npm test → # duration_ms 293.827708)
Task 15: Ruling: smoke step 1 showed two defects — the page grew with the thread so the composer slid off screen, and Grant posted a second News sentiment request while the seed one still waited — fixed with a css layout test and a pending list in the driver context, both RED then GREEN — cost if wrong: none.
Task 15: Ruling: the rest of the smoke walk passed with an empty console, and showed three more defects — the rail scrolled as a whole so Account slid off with many rows, the director palette covered the send key, and a SOL or ETH request got a BTC card — each fixed with a test RED then GREEN — cost if wrong: none.
Task 15: note: Export was checked by intercepting the anchor click in the page, so no file was downloaded; the IME composition path is covered by code reading, not by a browser run.
Task 15: complete (commits 097a3ca..29e093a, tests: npm test → # duration_ms 268.44275)
Final: the first review run failed at start on every agent, the Fable usage limit was reached; re-run on Opus, the session model and the most capable one available.
Final: review on Opus, five seats: whole-branch, spec conformance, state, wiring, layout; every Critical or Important finding was checked by three skeptics with distinct lenses, reproduce, spec and intent, severity, and kept on two of three. 14 survived from the dimension seats, many overlapping; the whole-branch seat added the answered-card chip.
Final: Ruling: re-graded four Minors to Important by what a person meets — + on an install request answered it before any install, three seats; the toast and banner outlived their moment and covered the next drawer's Install; Export could fail in Safari on this Mac; a pasted full address spilled out of its bubble — cost if wrong: four extra fixes.
Final: Ruling: re-graded the answered card's answer-by chip to Important — spec 6 ties the warn-fill chip to a card that still needs a decision, and on an answered card it misleads; the answered card now shows its answer, and the plan test that pinned the old chip moved to an unanswered card — cost if wrong: one chip.
Final: fixed narrow windows: below 860 px the rail is a block above a page that scrolls as one — css test narrow windows RED to GREEN, browser check at 700 px, suite 111/111.
Final: fixed the just-installed chip missing on shelves and showing for an uninstalled plugin — discover test the shelves show the just-installed card too RED to GREEN.
Final: fixed message kinds 8 and 10 unreachable — driver test the director can show the door's refusal and the close, app-dom test the director opens the first-run state, the refusal and the close, RED to GREEN.
Final: fixed group @-mentions unanswered, bots proposing in groups, and + 加个 bot taking every bot — driver test in a group the @named bot answers, reducer test the new-message draft picks bots one by one, messages-screen test F7 picker, RED to GREEN.
Final: fixed the teaching conversation answered by Gravit — driver test a teaching conversation is answered by the plugin it teaches, reducer test an install conversation knows which plugin it teaches, RED to GREEN.
Final: fixed the signature table letting every plugin propose — discover test the signature follows the plugin RED to GREEN.
Final: fixed F6 unreachable — data test firstRun and the director key, RED to GREEN.
Final: fixed Stop and Withdraw leaving answers live — reducer test a stopped or withdrawn conversation is closed, thread test a stopped conversation shows no answer keys, RED to GREEN.
Final: fixed limit lines ignoring the real limit and spent never moving — driver test limit asks read the real limit, reducer test a filled receipt adds to spent, app test answerFlow hands the driver the real limit, RED to GREEN.
Final: fixed the composer keeping the sent text — app-dom test the composer is empty right after a send RED to GREEN, browser check.
Final: fixed every re-render resetting scroll — app-dom tests for the thread and for page, rail rows, drawer and shelf rows RED to GREEN, browser check on Discover.
Final: fixed IME composition broken by a reply landing mid-pinyin — app-dom test nothing re-renders while an IME is composing RED to GREEN; a real IME was not driven in the browser.
Final: fixed focus dropping to body, drawers and the call never taking focus — app-dom tests for focus and for the call RED to GREEN.
Final: fixed the toast over the drawer, never leaving, and persisted moments — css test, app test watchToast, app test a saved state boots without moment-only overlays, reducer test leaving Discover clears its drawer, ask and toast, RED to GREEN, browser check of the 6 s toast.
Final: fixed + on an install request answering before the install — app-dom test + on an install request leaves it waiting, reducer test installing answers every waiting ask, RED to GREEN.
Final: fixed Export revoking in the same tick — app-dom test Export revokes later RED to GREEN; Export was not clicked in the browser, no file was downloaded.
Final: fixed long words spilling out of bubbles, and chips breaking per character on shelf cards — css tests RED to GREEN, browser check.
Final: fixed the answered card's deadline chip — thread test RED to GREEN.
Final: Ruling: DOM wiring is tested through tests/helpers/fake-dom.js, a hand fake that runs boot under node:test, because the plan's constraint forbids a DOM library in tests — cost if wrong: the fake can drift from a browser; the browser checks above cover the main paths.
Final: Ruling: a drawer that just opened starts at its top; scroll is kept only while the same drawer stays — the scroll test was corrected to that — cost if wrong: none.
Final: Ruling: the reviewers' set-aside items, each kept as the code has it — buttons without handlers (attach, mic, Phone, Email, Top up, Take back, Move, Receive, Statement, Connect, 换一张图) are the plan's not-built list; native prompt and confirm stay as the editing UI of a pure front end; Markets and Trade stay stubs; section 9 back-end seams stay out by the operator's word — cost if wrong: these controls look live and do nothing.
Final: Ruling: kept as built — --on-equity as a second token, and white on the Black equity blue at about 3.7 to 1, both follow spec 3.1 and 5.2 and the pre-flight ruling, the operator's call — cost if wrong: one token and a contrast tweak.
Final: Ruling: kept as built — thread cards drawn as bubbles with an edge, not the page card's 18/20 padding and radius 16, per spec 5.2 and 6; limit and install keys left-aligned, per spec 5.3 for plain bubbles; the card + installing straight from the shelf, since spec 7.3 gives the card an Install key — cost if wrong: layout tweaks.
Final: Ruling: kept as built — the Memory switches change nothing, the card deadline is not enforced, rows are not reordered by the latest message, a public upload installs at once, publish opens no teaching conversation, a Done conversation keeps its status when replies arrive — spec 8, 9 and 11.2 leave these to the back end or open — cost if wrong: small behaviours to add.
Final: Ruling: kept as built — a v:1 save of a broken shape would crash render; no released build wrote another shape, and any later shape change must bump SEED_VERSION — cost if wrong: a blank page until localStorage is cleared.
Final: Ruling: kept as built — two tabs share one save with last write wins; pending replies are lost on reload; the static server serves the whole folder on 127.0.0.1 only; arriving messages are not announced to screen readers; text inputs keep outline none with a visible caret; shelf scrollbars are hidden with See all as the way through — cost if wrong: robustness and accessibility polish.
Final: Ruling: kept as built — silhouette portraits, the F1 head form, the exact --down-edge, and dividers mixing Today with 昨天 are open in spec 11 or copy choices — cost if wrong: none now.
Final: minor (deferred): the incoming call is a modal over a scrim rather than a red-edged card, and the rail's Phone and Email keys do nothing.
Final: minor (deferred): the group head's members line and card meta are 13 px where the spec says 12 px.
Final: minor (deferred): uploaded plugins never join their kind's shelf, and the Installed view lists an uninstalled own plugin under 你上传的.
Final: minor (deferred): Stop and Withdraw write a centred system line, where spec 5.2 keeps dividers as the only centred lines.
Final: minor (deferred): no Monitor ever posts a signal; only the Crypto fraud tool does.
Final: minor (deferred): the director's bot line can land in a conversation Buffett is not in.
Final: minor (deferred): breaking-news and call messages that land off screen leave no unread dot and bypass the stopped guard.
Final: minor (deferred): a memory added by hand goes into a fourth group, 你加的.
Final: minor (deferred): an unknown shelf route shows an empty Discover grid.
Final: minor (deferred): uninstalling and reinstalling opens a second identical teaching conversation.
Final: minor (deferred): an uninstalled fraud tool still speaks in the address flow, and Details keeps listing removed plugins.
Final: minor (deferred): no-op actions still notify and save.
Final: minor (deferred): no divider when a gap under 15 minutes crosses midnight; 昨天 reads as M/D for an hour after a spring-forward day.
Final: minor (deferred): pressing + while a draft is open wipes the draft.
Final: minor (deferred): initials and auto-titles can split an emoji into a broken character.
Final: minor (deferred): a whitespace-only plugin name clears the upload form without publishing.
Final: minor (deferred): Change limit asks its second question after the first was cancelled.
Final: minor (deferred): Cancel on a new message lands on the first conversation, and Back then wastes a step.
Final: minor (deferred): serve.js hangs a request if the file read fails after the 200 header.
Final: minor (deferred): ARIA — a role=button card wraps buttons and a link, the director is role=menu without menu items, and the radio groups have no group label.
Final: minor (deferred): between 808 and 1099 px the Details drawer covers the send key while open.
Final: minor (deferred): the group row's second avatar shows a ring on the current and hovered rows.
Final: minor (deferred): the banner is centred on the viewport and overlaps the rail below about 1056 px.
Final: minor (deferred): composer text follows you between conversations.
Final: minor (deferred): Portfolio shows an empty sparkline box.
Final: minor (deferred): render tests pin attribute order.

## Round 2 — the operator's 2026-10-10 requests (spec §13)
Round 2: built on feat/gravit-ui in 7abea67..5359a9d (Discover keys + 我的插件 + Create connector, connector secrets kept out of localStorage, two-level navigation, in-page controls, files + mic, phone + mailbox, Account panels, two focus/file fixes, docs); branch kept as it is, nothing merged or pushed.
Round 2: Ruling: SEED_VERSION goes to 2, so a round-1 save is dropped once and the new seed (mailbox, venues, activity, lastConv) loads — the new state shapes would crash render on an old save — cost if wrong: the operator's round-1 demo state is reset once.
Round 2: Ruling: the new controls are scripted stand-ins with no network: 连接 answers after 1.2 s with tools named from the address, the mic writes a sample sentence after 1.8 s, Gravit picks up a call after 1.5 s, a venue connects after 1.2 s, the mailbox holds three seeded letters — spec 13 says the front end is pure — cost if wrong: these need a back end later, as spec 9 already says.
Round 2: review — workflow wf_309acf71-657, four lenses (requests, state, wiring, layout) with three-lens adversarial verification on default Opus; eleven distinct Important defects survived (A–K below), all fixed in df066f8.
Final: Ruling: kept Top up Important where one verifier graded it Minor — the USDC holding went negative, money from nothing on a money screen — cost if wrong: none, the guard is one line.
Final: fixed A, switching editors carried the last editor's text into the next (Memory overwritten, draft limit changed) — opening another editor starts from its own value, not the text left in the last one RED→GREEN, suite 156/156
Final: fixed B, Details kept offering Withdraw, Stop and End limit where their second press did nothing — Details offers only what still works: no Withdraw or Stop once closed, no End limit without a limit RED→GREEN, suite 156/156
Final: fixed C, Top up had no ceiling — Top up cannot take more than your USDC holding RED→GREEN, suite 156/156
Final: fixed D, drawers stacked (mailbox over a plugin, panel over Settings) and an Account panel followed you off Account — one drawer at a time: each opener closes the others, and an Account panel does not follow you off Account RED→GREEN, suite 156/156
Final: fixed E and F, Details covered the send key between 1100 and 1399 px, and at 1024 px the column was 504 px with the group head colliding — Details never covers the conversation: it makes room, folding the list away on a medium window; the first level folds to icons below 1180 px RED→GREEN, suite 156/156; checked in the browser at 1280 (thread 660 px, send key 847 vs drawer 880), 1024 (group head clear; with Details send 591 vs drawer 624) and 800 (Working and Details back in the flow)
Final: Ruling: the list folds away under 1400 px while Details is open, not under 1280 — at 1280 with the list the conversation was 360 px — cost if wrong: one number.
Final: Ruling: between 861 and 1180 px the first level folds to icons by itself and its chevron hides — at 1024 the open first level left the conversation too narrow — cost if wrong: the operator's open choice is overridden at medium widths.
Final: Ruling: the group head reserves 200 px each side for Working and Details — the task line stays centred and never runs under them — cost if wrong: long task lines shorten sooner.
Final: fixed G, the Move pickers reset on every render — the Move pickers keep their choice across a render, such as an error RED→GREEN, suite 156/156
Final: fixed H, Enter on an editor's × saved — Enter on an editor's × key does not save RED→GREEN, suite 156/156; the same guard skips Enter while an IME is composing (isComposing or keyCode 229)
Final: fixed I, focus fell behind an overlay when the pressed key went away — focus goes to what replaced the pressed key: the confirm, or the drawer, never the page behind an overlay RED→GREEN, suite 156/156
Final: fixed J, focus jumped to the wrong Account panel key — focus returns to the same panel key, told apart by every data attribute RED→GREEN, suite 156/156
Final: fixed K, a live call redrew the page each second and dropped presses — a live call updates only its timer each second; the page is not redrawn under the keys RED→GREEN, suite 156/156
Final: fixed in passing by the same changes — the IME Enter minor, the mailbox over an Account panel, a hidden editor taking the first Escape; and two round-1 minors, the rail's Phone and Email keys doing nothing and Details covering the send key between 808 and 1099 px.
Final: Ruling: kept as not checked — a real IME, Safari and Firefox (clipboard, downloads, rendering), screen readers, phone widths under 700 px and fidelity to the canvas boards were outside what automation could drive — cost if wrong: platform polish found later by hand.
Final: minor (deferred): the connector's address field is type=url, so the browser's own bubble pre-empts the in-page error; https://localhost is refused with the wrong reason and http:// is accepted.
Final: minor (deferred): the collapsed strip's phone key, mail key and expand chevron have no title.
Final: minor (deferred): inline editors show bare boxes with no visible label; Top up and Take back look the same.
Final: minor (deferred): uninstalling within 6 s of an install leaves the 装好了 toast up.
Final: minor (deferred): a closed connector's tool list can land in the next connector; stale pickup and mic timers act on the next call or listen; resetting during a live call freezes the next call's timer at 00:00.
Final: minor (deferred): amounts under a cent create or destroy money; Change limit accepts a total below what is spent; draft limit chips skip per-order ≤ total and 'until' has no upper bound.
Final: minor (deferred): one venue finishing its connection clears the connecting state of another.
Final: minor (deferred): after you call Gravit, the row preview still says Gravit 来电.
Final: minor (deferred): Copy address says 已复制 even when the copy failed; the Statement CSV has no BOM and opens garbled in Excel.
Final: minor (deferred): field errors are not announced to screen readers; keyboard focus on the connector's radios is invisible.
Final: minor (deferred): credentials typed inside a server address are saved with the plugin.
Final: minor (deferred): collapsed rail under 860 px has 22 px keys and a badge over the icon; small white-on-blue text in Black is 3.67:1.
Final: minor (deferred): the connector's radio segments stretch full width, and 取消 and 连接 scroll out of view at 800 px tall.
Final: minor (deferred): selects render in Arial and UA white; disabled Connect buttons look clickable.
Final: minor (deferred): calls you place and live calls wear the urgent red edge; muted and unmuted look almost the same in Black.
Final: minor (deferred): below 1100 px the sticky toast's Open key can sit under a drawer.
Final: minor (deferred): the Memory editor shows four round keys, misaligned; file chips flow inline with the owner's words.
Final: minor (deferred): the Receive QR is inverted in Black; the director opens under the connector's scrim.
Final: minor (deferred): dead size rules (the 32 px chevron, the --rail token); mailbox rows have square hover grounds and back links two colours.

## Round 3 — the operator's 2026-10-10 second requests (spec §14)
Round 3: built on feat/gravit-ui in bda98c1..720871d (no author or price line and no 刚装好; My plugins with no count; Mail as a screen; Create as Discover's own MCP face; docs); branch kept, nothing merged or pushed.
Round 3: design panel wf_c5725aeb-99a (three designers: spec-faithful, demo-story-first, developer-first; one judge) chose the story-first design with the spec-faithful signature grafted on.
Round 3: Ruling: the mail letters sit in the second-level column, where Messages keeps its conversations, not inside the main column as the judge drew it — Mail and Messages then read alike and the narrow layout comes free — cost if wrong: one render function moves.
Round 3: Ruling: the drawer's 怎么付 section went with the Free line — it said 免费 again, and the operator cut the price words — cost if wrong: one section to restore.
Round 3: Ruling: My plugins is the English name — the literal English of 我的插件, and it covers both 装了的 and 你创建的; Installed is the word the operator already replaced — cost if wrong: one label.
Round 3: Ruling: SEED_VERSION goes to 3, so a round-2 save is dropped once — the mailbox lost open/reading and the counters gained mail and run — cost if wrong: a viewer's saved demo state, Memory edits included, resets once.
Round 3: Ruling: the scripted client starts only on 复制 or the director's 插件上传, never by itself — the presenter sets the pace — cost if wrong: a presenter who opens Create and waits sees 等待连接.
Round 3: Ruling: a private upload is published and installed by one signature; a public one is published only, reviewed for 5 s, then installed by the drawer's usual signature — spec 7.7 reviews public plugins first and installing needs the owner's signature — cost if wrong: the author waits for review before using their own public plugin.
Round 3: Ruling: your own private uploads lead their kind's public shelf in your view, as the seeded private Pairs already sits on Quant — cost if wrong: an outsider may read a private card as public; only the drawer says Private.
Round 3: Ruling: the director moved above the dialog's scrim (z-index 49, below the call at 50) — 插件上传 now drives the dialog — cost if wrong: none.
Round 3: found and fixed in passing: a stray closing brace left by the round-2 layout fix (df066f8) made browsers drop the .drawer-head rule, so every drawer head lost its row, padding and hairline — app.css is well formed: braces never close more than they opened RED→GREEN (4a6a6d0).
Round 3: review wf_f3496c47-eb6, four lenses (requests, state, wiring, layout in a real browser) with three-lens verification of every Critical or Important finding; no Critical; all four lenses report the four requests met.
Final: fixed the search box keeping old words after Publish or 插件上传 cleared the search — when Publish or 插件上传 clears the search, the search box is cleared too RED→GREEN, suite 167/167 (fdb5308)
Final: fixed below 860 px the Mail inbox standing alone cut at 40vh — narrow windows, the toast under a drawer, and long words that wrap (new assertion) RED→GREEN, suite 167/167; checked at 800x900
Final: fixed the Create dialog moving under the pointer as its height changed — the dialog body keeps its scroll while the same step changes, and starts at the top on a new step, plus the dialog hangs from the top (css assertion) RED→GREEN, suite 167/167; checked at 1280: top stays 64 px across a client switch
Final: fixed 复制 reading as plain text on the code box — css assertion RED→GREEN, suite 167/167
Final: Ruling: re-graded to Important and fixed — after 拒绝 the director's 插件上传 did nothing (found by all four lenses as Minor) — after 拒绝, the director's 插件上传 starts a fresh upload in a new dialog RED→GREEN, suite 167/167 — the director is the presenter's tool and a silent no-op breaks the story — cost if wrong: none.
Final: Ruling: re-graded to Important and fixed — cards in My plugins, See all and search collapsed into one tall column because a grid card wore the container's class grid (layout lens, Minor; present since round 1) — search shows a results grid; a shelf route shows that shelf as a grid with a way back RED→GREEN, suite 167/167 (6f7d461) — every grid view a person opens was broken — cost if wrong: none.
Final: Ruling: kept as not checked — Safari and Firefox, screen readers, and whether the Cursor and Codex config lines match those clients' current versions (the claude mcp add line is the real form) — cost if wrong: a pasted line needs a tweak; the stand-in address resolves nowhere anyway.
Final: minor (deferred): after 复制 the client switch still takes a click for 1.5 s, so another client is highlighted beside the first client's line.
Final: minor (deferred): Escape closes the dialog under the director instead of the director on top of it.
Final: minor (deferred): Tab leaves the Discover MCP dialog for the page behind its scrim (no aria-modal, no focus trap).
Final: minor (deferred): under about 778 px tall, Publish and 拒绝 of the first upload sit below the fold of the dialog's scrolling body.
Final: minor (deferred): at about 700 to 803 px and 861 to 871 px wide, My plugins and Create split onto two rows.
Final: minor (deferred): the Claude Code line wraps inside its address at stand- | in/mcp.
Final: minor (deferred): an open letter's grey sender mark disappears into its row's grey highlight.

## Round 4 — Markets and Trade after Linqi's buyer-agent-demo (spec §15)
Round 4: the operator's words "Markets和trade的前端借鉴Linqi的buyer-agent-demo"; built in 7583e14..da6d886 (data and domain, the screens, docs 2b5021a, review fixes); branch kept, nothing merged or pushed.
Round 4: understanding workflow wf_4205fec1-651 — readers over Linqi's ui/markets.js, ui/trade.js and the shared shell (read from the primary checkout's demo/ at 0ef5131; this worktree's demo/ is empty), one agent on his live stand-in page (offline: network blocked, payments refused, a scratch home; it placed one $20 SOL stand-in buy and paired the browser pane with that stand-in; nothing under demo/ changed), one reader on gravit-ui; a designer wrote the plan.
Round 4: Ruling: four kinds only — Crypto, Stocks, RWAs, Predictions; Perps and Pre-IPO need a margin model and Memory says 不碰杠杆 — cost if wrong: two tabs and a position model to add.
Round 4: Ruling: quotes are stand-ins held still — what is shown is what fills and the tests stay exact; a resting limit never fills — cost if wrong: Linqi's ticking tint and price drift to add.
Round 4: Ruling: Sign and place stands in for Linqi's device-key signature; the prepared order, What you sign and the ten-minute window stay — cost if wrong: none for a demo; the back end of §9 carries the real signature.
Round 4: Ruling: a hand order is the owner's, capped at the account's $100 a move and never drawn from a conversation's limit; Hand to Gravit instead opens gravit's New message with the words and the limit chips instead of Linqi's agent composer — cost if wrong: one more surface to port.
Round 4: Ruling: the market drawer is the route #/markets/<id>, so it is never stored and a ticker links straight to it — cost if wrong: none.
Round 4: Ruling: Linqi's class names are renamed mk-* and tk-*; his .card, .quote, .spark, .empty, .tabs, .t, .yes and .no would restyle gravit's own — cost if wrong: none.
Round 4: Ruling: SEED_VERSION goes to 4 (holdings with quantities, cash at the venues, account.orders, the watchlist, the ticket) — cost if wrong: a viewer's saved demo state resets once.
Round 4: Ruling: the plan's "sell 1 BTC → Sells only what you hold" test could not happen (the cap refuses first); the held check is tested with a 0.3 NVDA sell — cost if wrong: none.
Round 4: review wf_465c2b2c-3d2, four lenses (fidelity to Linqi, domain and money, wiring and focus, layout in a real browser) with three-lens verification; one Critical, eleven distinct Important survived, all fixed in da6d886; suite 220/220.
Final: fixed the Critical — a limit sell was valued at its limit, so a sell under the bid slipped under the $100 cap and filled for thousands — a limit sell is worth what it will fill at, never less than the bid, so the cap holds RED→GREEN, suite 220/220
Final: fixed dollar market buys sized at the ask, so $100 was refused — a market buy in dollars is sized at the worst price it may pay, so $100 fits $100 a move RED→GREEN; the worked numbers moved (the $150 refusal now reads $149.90, $20 SOL buys 0.133, $50 USDY buys 44.34)
Final: fixed the clock dying after Reset demo or 空白开始 (and the call timer with it) — after Reset demo the signature clock still runs on Trade RED→GREEN; the countdown now rounds down, which also ended a flaky first-second "10:00"
Final: fixed a held prediction that could not be sold — a held prediction sells from its drawer and from the picker RED→GREEN
Final: fixed moving a holding's full shown value leaving a negative quantity — moving all of a holding moves it whole RED→GREEN
Final: fixed Back reopening a closed market drawer — closing a market drawer replaces its history entry RED→GREEN
Final: fixed Watch and Connect inside the drawer sending focus to the table row behind — Watch inside the drawer keeps focus inside the drawer RED→GREEN (focus keys are looked up inside the same drawer, dialog or ticket first)
Final: fixed the table beside the drawer showing only names — the css assertion for 24h and Volume folding RED→GREEN; names wrap from a 140 px minimum and the key drops its icon; checked at 1280: table 492 px in a 491 px box, price and key in view
Final: fixed the ticket jumping to its top on every keystroke, and opening off-screen on narrower windows — the ticket keeps its own scroll while you type, and a new ticket is brought into view with the amount ready RED→GREEN
Final: fixed the ticket's Connect to trade rendering as a grey native button — the button.link css assertion RED→GREEN
Final: fixed the sort carrying across tabs and the search count covering every tab — a tab starts from Most traded …; the search count is what the tab shows RED→GREEN
Final: Ruling: re-graded to fix as cheap and visible — the doubled "Gravit asks: 要你答：", a 0% class on the allocation bar, selects in Arial — tests RED→GREEN — cost if wrong: none.
Final: Ruling: kept as deferred, graded Minor by effect — Move puts USDC at a venue as a holding the ticket does not count as money to trade with there (the venues' own cash covers every scripted order) — cost if wrong: a moved-USDC trade is refused with the venue's cash figure.
Final: Ruling: kept as not checked — Safari and Firefox, screen readers, and every difference from Linqi's live page beyond what the readers and the fidelity lens compared — cost if wrong: polish found by hand.
Final: minor (deferred): the ticket at rest has no Market search or list, and the picked row has no Change (Linqi's has both).
Final: minor (deferred): Trade rounds venue prices to cents ($1.11 for USDY) where Linqi shows the venue's precision; the limit placeholder is Math.round of the price ('0' for DOGE).
Final: minor (deferred): Under way drifts from Linqi's — no Cancel all, cards after orders, a 0 count shown, "0 filled", and prediction orders not worded in contracts.
Final: minor (deferred): the kind block and the quote drop the quote currency (USDT, USDC, USD) and his per-kind lines (no 24h for stocks, the RWA issuer box, "none held").
Final: minor (deferred): Watching reuses the market row instead of his watch row; the USD Coin drawer drops his Price and Agents parts; Across venues shows Buy at and Spread for USDY and spreads on public rows; Gravit on it does not list Gravit's open orders.
Final: minor (deferred): picker rows differ from his; a Most traded or Recent row hands focus to the You hold row of the same market.
Final: minor (deferred): a sell is not re-checked against what is held when it fills; Gravit's scripted $5 BTC buys are below the BTC minimum the owner's ticket enforces; a limit's room in Gravit on it can print float subtraction.
Final: minor (deferred): Account's holding rows do not say which outcome a prediction holding is (the plan's account.js change was not made).
Final: minor (deferred): focus falls to the page after Sign and place, × on the ticket, Clear, a cancel confirm on Trade and Hand to Gravit from the drawer; Hand to Gravit replaces half-written composer text.
Final: minor (deferred): two overlapping Connect to trade presses clear each other's Connecting…; d on a focused ticket select opens the director; Escape ending an IME composition in the search also closes the drawer.
Final: minor (deferred): at 1280x800 the docked ticket runs to the window's bottom edge; What you sign has no disclosure marker and a 28 px target.

## Round 5 — the re-laid canvas against the build (spec §16)
Round 5: the operator's words "画布更新了，你再看看"; a comparison workflow found 132 differences (30 code, 65 canvas, 37 operator); the operator answered pages for plugins and markets, label/value Details, Venues on their own segment, and "改代码那 30 处，改正画布上画错的板，spec 和 ledger 跟着更新". Built in 288c13f (pages), 901ae91 (catalogue), 089bff2 (conversation, banner, calls, composer, controls, levels), e8697c4 (Account, Memory, Mail, Create, Trade); tests first for each batch (8, 23 and 7 failing tests watched red, then green).
Round 5: Ruling: the operator items left unanswered took the defaults announced with the comparison — appearance follows the boards, behaviour stays as built (15-minute dividers, list order, the alert kind kept and written into §6) — cost if wrong: a few CSS values or a board to flip.
Round 5: Ruling: a plugin and a market are routes of their own (#/plugin/<id>; #/markets/<id> renders the page instead of the list); Back is the browser's, the page's ‹ link returns to the Discover route it came from (lastDiscover) or to Markets — cost if wrong: none.
Round 5: Ruling: kind 7 happens as a director event from Telegram monitor without installing it, so F11's four installed plugins stay true — cost if wrong: Telegram monitor would join the seed.
Round 5: Ruling: the breaking banner sits in a fixed zone that starts where the first and second levels end (sibling selectors on the order app.js renders: rail, list, main, overlays), so it never scrolls with a page; it drops in once per banner id because every store change re-renders — cost if wrong: one CSS rule per new level.
Round 5: Ruling: a call's level follows its answer (red while ringing or missed, white once connected or cancelled), in levelOf; when you ring Gravit it picks up about BTC with a scripted line of what it said — cost if wrong: none.
Round 5: Ruling: the mic streams its scripted sentence word by word over its 1.8 s; a press before the end writes the whole sentence; words typed meanwhile are overwritten while it listens — cost if wrong: typing during a listen loses those words.
Round 5: Ruling: Receive needed an owner wallet the seed did not have — account.receive (Stand-in Wallet, USDC on Base, 0x9a7c…d41e); SEED_VERSION 5 — cost if wrong: a saved demo resets once.
Round 5: Ruling: F6's hint line stays off (decision 9 over §2/§5.7's "one line"); the English sentence went to F16 — cost if wrong: one line back on the empty state.
Round 5: Ruling: the picker marks only the first row that names the open ticket's market (You hold before Most traded) — cost if wrong: none.
Round 5: note: two full-suite runs took 15 minutes; the power log showed the Mac on battery entering sleep for 903 s mid-run (real-timer tests freeze across it), not a hang in the code; later runs were 27 s.
Round 5: review wf_679cdc53-f1d (three lenses: behaviour, layout and accessibility, tests; one verifier per lens) — its behaviour reviewer died on a network error while the Mac slept, so that lens ran again as wf_101d4154-765; every finding reproduced (fake DOM, node renders, Chromium measures); one fix pass, each fix test-first, suite 264/264.
Final: fixed the banner squeezed to 100–330 px and off-centre when Details folds the list at 861–1399 px — with Details folding the list, the banner zone starts where the first level ends; over an Account drawer it leaves 460 px RED→GREEN
Final: fixed Install and Uninstall on a plugin page dropping focus to the page body — a plugin page's one key keeps its id across Install and Uninstall RED→GREEN
Final: fixed the way back losing focus at the next re-render (a reply, a toast, the clock) — the way back on a plugin or market page keeps focus through a re-render RED→GREEN (re-graded from Minor: on a market page the clock re-renders every second)
Final: fixed Send during a listen putting the sent words back and typing during a listen being wiped — Send during a listen stops the mic …; typing while it listens is kept RED→GREEN (re-graded from Minor by effect)
Final: fixed coming back from a market or plugin page at the top of the list with focus on the page body — back from a market page, the list is where you left it and focus is on the row that opened it RED→GREEN (re-graded: every peek at a market lost your place)
Final: fixed the editor boxes' accessible names shrinking to their visible words ("on", "days") — an editor names each box … (aria-label "Dollars an order", "Trade on venue", "Days until it ends", "Top up amount") RED→GREEN (re-graded: a regression this round introduced)
Final: fixed Discover's dialog staying open and unseen on a plugin page, and a plugin page reached from a conversation's + going back to an old shelf — Discover's dialog does not follow you onto a plugin page; a plugin page opened from a conversation goes back to Discover itself RED→GREEN
Final: fixed a page opened while an Account panel or Details was open leaving focus on the body — a page opened while an Account panel is open takes focus on its way back RED→GREEN
Final: fixed a market page's cancel confirm dropping focus — on a market page, No returns focus to the Cancel key; Yes, once the order is gone, to the way back RED→GREEN
Final: fixed a public upload passing review on its own page leaving the In review toast up — a public upload passing review while you are on its page says so there (no Open on its own page) RED→GREEN
Final: fixed plugins made through Create still saying the old never line — a plugin you made says Never the way the catalogue does RED→GREEN (one NEVER constant)
Final: fixed the market page's facts and issuer boxes vanishing into the page ground (they were drawn for the white drawer; found by the canvas check) — on a market page the facts box and the issuer box stand on white RED→GREEN; F22 follows
Final: fixed two canvas-round CSS assertions that still passed with their rule removed — tightened to the exact rules
Final: Ruling: the Trade picker's open-ticket mark keeps --bg as F23 draws it (about 1.1:1 on the card; aria-current carries it for screen readers) — the operator's default was "appearance follows the boards" — cost if wrong: a stronger mark (surface-2 and an inset rule) in one CSS line.
Final: minor (deferred): the canvas boards draw with content-box sizing where the code is border-box (list rows 80 px against 64, line keys 46 against 44, thread keys 34 against 32); a canvas-wide pass, not this round's.
Final: minor (deferred): the boards draw Mail and Account as buttons where the code has links; the incoming-call specimen on F15 keeps its own padding and radius instead of the 320 px dialog.
Final: minor (deferred): no board shows Markets' Predictions tab with its Yes/No cards; F20's refused step was added as a specimen, F21 shows the All tab only.
Round 5: canvas corrected by workflow wf_2bfeccec-da8 (nine correctors, nine checkers over local copies), F16 rewritten by hand (this round's removed sentences, §15.5's Linqi sentences, F19/F20, My plugins, the page), rows re-laid for the taller F19/F20/F21/F16 (rows at y 0, 1320, 2640, 5060, 6840, 8660), published as canvas version 55.
