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
