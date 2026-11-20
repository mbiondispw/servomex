# Servomex Integrated Quoting — Demo Playbook

How to demo Salesforce Revenue Cloud as the replacement for Servomex's
**Systems Margin Calculator** spreadsheet. The storyline, pricing logic and pain
points come from a real Servomex quote, so the audience sees their own deal
quoted without the spreadsheet. The demo swaps that deal's analyser for the
**SERVOFLEX MiniMP 5200**, whose option matrix makes a stronger configurator
showcase.

| | |
|---|---|
| **Source analysed** | `621044384_MarginCalc(r2v9).xlsx`. Customer file, kept locally in `.customer-files/` and not committed |
| **Primary tab** | `Pricing Sheet_LC`: the input and calculation sheet in the selling currency |
| **Reference deal** | LyondellBasell, opportunity `[A2204] LyondellBasell CVO POSM1 2700 with SYSTEMS`, SAP quote `621044384` Rev 2, USD, Americas |
| **Demo analyser** | 4 × SERVOFLEX **MiniMP 5200**, user-configured, replacing the deal's 4 × `02700D1`. Options come from the [public product page](https://www.servomex.com/gas-analyzers/finder/minimp-5200/). **Prices are illustrative** (§7.1) |
| **Template version** | Rev 9 (2021-01-15) |
| **Audience** | Servomex Sales, Inside Sales/CSR, Systems/Proposals, Service, Finance/Project Controls |
| **Target length** | About 50 minutes for the core flow, plus 15 minutes of optional acts |

---

## 1. Executive summary

The margin calculator is far more than a pricing sheet. It holds **pricing
policy**, the **cost model**, **approval evidence**, a **proposal-to-SAP line
mapping**, a **cash-flow forecast** and an **installed-base forecast**. All of it
sits in 14 tabs, and people re-key the results between SAP, Excel and
Salesforce at least four times per deal.

Of the original $353,807 workbook quote, **71% ($249,857) is priced by spreadsheet
formula** rather than by SAP list price. Only the analysers and the S2700
spares kit come from a price list. The rest depends on hard-coded constants
that disagree with the template's own instructions (see §4).

**The best demo flow:** quote the LyondellBasell deal end-to-end in Revenue
Cloud with **MiniMP 5200** analysers, following the 16 steps of Servomex's own
*Overall Process* tab. The demo baseline is **$299,291.55** (§3.2). Build the
demo around four moments:

1. **Constraint-checked configuration.** Pick a MiniMP variant or a
   user-configured build. Pump-only options appear only when the pump is
   selected, a second measurement is offered only on user-configured builds, and
   the price follows each option.
2. **"Change one number" cascade.** Change the system quantity or add a
   discount. Spares, warranty, packing, contingency, commission and both
   margins recalculate on the quote line. Nobody has to "redo the margin
   calculator to match" (process steps 9, 13 and 16).
3. **Guardrailed discounting.** Sales discounts but cannot touch cost. The price
   waterfall exposes buried discounts, such as the hidden **29.466%** on the
   analyser warranty line. A margin breach routes the quote to Finance
   automatically.
4. **One record from quote to order.** The approved quote becomes the proposal
   document, the order and the source for billing milestones and installed
   base. The workbook is never attached as a file again.

---

## 2. How the workbook is built

| Tab | Role | Inputs | Feeds |
|-----|------|--------|-------|
| Rev Log | Template change history: 10 revisions in 3 months, mostly formula fixes | — | Summary |
| Overall Process | 16-step US Systems quoting process and tab instructions | — | — |
| Summary | Management view by category, always in **GBP**, plus payment milestones | Milestone % | Approval |
| SAP Line Items | Maps calculator lines to the **customer-facing SAP quote lines** | — | SAP quote |
| **Pricing Sheet_LC** | **Main input and calculation sheet in the selling currency** | Blue cells | Everything |
| Pricing Sheet- GBP | Full duplicate of the LC sheet converted to GBP | — | Summary |
| Systems Labour | Engineering, electrical and piping hours × rate by **build location** | Hours, location | Pricing, SAP |
| Service | FAT, drift test and training (hourly), plus SAT, commissioning and mobilisation (daily), by **service region** | Days, region | Pricing, SAP |
| 3rdpty-Integrator | Subcontracted systems, factored items and site services: cost → price at a target margin | Cost, margin % | Pricing |
| Cash Flow | 6-month cost and billing curve, net cash position | Manual overrides | Summary |
| Install Base Rev | 10-year service revenue potential | Potential by service type | Summary |
| Lookup Tables *(hidden)* | FX matrix (GBP/USD/EUR/RMB/INR), labour and service rate cards with annual % uplifts, T&C options | Finance monthly | All |
| Margin Sheet / SFDC Instructions *(hidden)* | Usage rules: required for orders over £75K, €75K or $125K; attach the file to the SFDC opportunity | — | — |

### 2.1 `Pricing Sheet_LC` calculation model

Every line follows one pattern: `Ext List = Qty × List`, then
`Sell = Ext List × (1 − Discount %)`, then
`Margin = Sell − Qty × Unit Cost`. Each section sets list price differently:

| Section (rows) | List price rule | Cost source | Reference deal |
|----------------|-----------------|-------------|----------------|
| **Analysers** (10–40) | Typed list price (SAP) | Typed unit cost | 4 × `02700D1` @ $24,788, cost $2,785.11 |
| **Systems Material** (43–72) | **Cost-plus**: `=I43/(1-0.4)` → 40% margin | Engineered BOM cost from Systems/Proposals | 4 × `ASYSTEM`, cost $22,533.42 → list $37,555.70 |
| **Factored Product** (76–90) | Cost-plus: `=I76/(1-0.35)` → 35% margin | Typed | Not used |
| Factored 16–26 (92–102) | From the 3rd-party tab at a target margin | Subcontract cost | Not used |
| **Spares** (106–108) | Commissioning spares = **5%**, 24-month spares = **15%** of the SAP systems line (discounted systems + labour) | **20%** of price | $8,746.34 + $26,239.02 + 2 × S2700SPARES @ $2,399 |
| **Systems Labour** (131–133) | Hours × sell rate by build location; one discount for the whole block | Hours × cost rate | 256 h (Houston: Eng $173/$96, Elec/Piping $71/$55) |
| Systems Integrator / 3rd Party Site (136–137) | From the 3rd-party tab | Subcontract | Not used |
| **Service Labor** (141–142) | Days × regional rate | Days × cost rate | In-house $3,744; on-site $8,896 |
| **Expenses** (146–166) | **Price = cost** (pass-through, 0% margin) | Packing `=3% × material+labour+service sell + $1,000`; drawings 4 × $450; docs 4 × $375 | $14,095.06 |
| **Extended Warranty** (170–171) | 6% × years × analyser sell, or × systems sell | **15%** of warranty list | $13,209.52, with a 29.466% discount on the analyser line |
| **Contingency** (174) | Cost only: `5% × total cost` | — | $7,254.16 |
| **Agent Commission** (183–187) | 15% analysers, 10% systems, 0% factored, 15% spares, 15% service, on sell | — | $37,758.58 |
| **Key Facts** (199–211) | Delivery = booking month + lead time; Incoterms; credit; T&Cs; competitive position | Dropdowns | FCA, Servomex Standard, credit adequate = **No** |

Two margins go to Salesforce by hand:

- **Contribution Margin** (`L178`): `(Sell − Cost incl. contingency) / Sell`. Labelled *"Use as Contribution Margin in Sales Force"*.
- **Net Margin** (`L190`): same, also net of agent commission. Labelled *"Use as Net Margin in Sales Force"*.

---

## 3. Numbers: source deal and demo baseline

### 3.1 Source deal as quoted (workbook)

All figures in USD from `Pricing Sheet_LC` and `Summary`, with 4 × `02700D1`.
A script independently re-implemented the model and reproduced these totals
exactly. They prove the pricing logic is understood. They are **not** the demo
targets, because the demo swaps in the MiniMP 5200 (§3.2).

| Category | Sell | Cost | Margin | Margin % | Share of quote |
|----------|-----:|-----:|-------:|---------:|---------------:|
| Analysers | 99,152.00 | 11,140.44 | 88,011.56 | 88.8% | 28.0% |
| Systems material | 150,222.80 | 90,133.68 | 60,089.12 | 40.0% | 42.5% |
| Spares | 39,783.36 | 7,481.57 | 32,301.79 | 81.2% | 11.2% |
| Systems labour | 24,704.00 | 16,704.00 | 8,000.00 | 32.4% | 7.0% |
| Service labour | 12,640.00 | 3,284.00 | 9,356.00 | 74.0% | 3.6% |
| Expenses | 14,095.06 | 14,095.06 | 0.00 | 0.0% | 4.0% |
| Extended warranty | 13,209.52 | 2,244.37 | 10,965.15 | 83.0% | 3.7% |
| Contingency (5% of cost) | — | 7,254.16 | −7,254.16 | — | — |
| **Project total** | **353,806.75** | **152,337.29** | **201,469.46** | **56.94% CM** | 100% |
| Agent commission | — | 37,758.58 | | | |
| **Net project total** | **353,806.75** | **190,095.87** | **163,710.87** | **46.27% net** | |

GBP view (Summary tab, FX 0.732493): project total **£259,161.11**, net
margin £119,917.14.

Commercial terms: payment milestones are 10% on order, 15% on drawing
submittal, 25% at FAT or build complete and 50% at shipment. Order lead time is
6 months. Incoterms are FCA. The 10-year installed-base potential is
£122,374, of which £48,076 is committed with the order.

### 3.2 Demo baseline with MiniMP 5200 (acceptance criteria)

The same deal and workbook logic, with two changes:

- **Analysers:** 4 × MiniMP 5200, user-configured as in Act 2 (§6). The
  illustrative list price is $13,000 and the cost $3,250 (§7.1).
- **Analyser spares:** 4 × MiniMP 2-year spares kit at an illustrative $240 list
  and $60 cost, replacing 2 × `S2700SPARES`.

Everything else is unchanged: systems, labour, service, expenses, the 6%
warranty with its 29.466% analyser-line discount, 5% contingency and commission
rates. Use these totals as acceptance criteria for the demo org.

| Category | Sell | Cost | Margin | Margin % | Share of quote |
|----------|-----:|-----:|-------:|---------:|---------------:|
| Analysers (4 × MiniMP 5200) | 52,000.00 | 13,000.00 | 39,000.00 | 75.0% | 17.4% |
| Systems material | 150,222.80 | 90,133.68 | 60,089.12 | 40.0% | 50.2% |
| Spares | 35,945.36 | 7,237.07 | 28,708.29 | 79.9% | 12.0% |
| Systems labour | 24,704.00 | 16,704.00 | 8,000.00 | 32.4% | 8.3% |
| Service labour | 12,640.00 | 3,284.00 | 9,356.00 | 74.0% | 4.2% |
| Expenses | 12,565.36 | 12,565.36 | 0.00 | 0.0% | 4.2% |
| Extended warranty | 11,214.03 | 1,820.01 | 9,394.02 | 83.8% | 3.7% |
| Contingency (5% of cost) | — | 7,237.21 | −7,237.21 | — | — |
| **Project total** | **299,291.55** | **151,981.33** | **147,310.23** | **49.22% CM** | 100% |
| Agent commission | — | 30,110.08 | | | |
| **Net project total** | **299,291.55** | **182,091.41** | **117,200.14** | **39.16% net** | |

Line detail: commissioning spares $8,746.34 and 24-month spares $26,239.02 (both
unchanged, because they derive from systems value), packing and handling
$9,265.36, and analyser warranty list $3,120.00, of which $919.34 is the hidden
discount.

### 3.3 What-if scenarios for the demo

Computed with the workbook's own logic on the MiniMP baseline. These are the
"expected results" for the live demo.

| Scenario | Total sell | CM % | Net % | Why it is interesting |
|----------|-----------:|-----:|------:|----------------------|
| Baseline | 299,291.55 | 49.22% | 39.16% | Passes the 35% net-margin rule |
| Sales gives **15% on systems** | 270,088.24 | 44.47% | **34.41%** | A $22,533 direct discount removes **$29,203** from the quote because spares, packing and warranty all derive from systems value. Net margin crosses the 35% threshold → approval |
| 10% analysers + 15% systems | 264,512.18 | 43.38% | 33.40% | Stacked discounts |
| Customer PO drops to **3 systems**, 15% systems discount kept (labour scales) | 221,083.35 | 46.36% | **36.03%** | Order differs from quote (process steps 12–13). Net margin is back above 35%, so the margin rule no longer fires |
| Same, but **labour left at 4 systems' hours** (workbook behaviour) | 228,716.88 | 46.02% | 35.95% | Labour hours are typed as `=4*16`, `=4*24`, so they **do not follow system quantity**. A $7,634 overstatement the spreadsheet never flags |
| 3 systems, no discount | 242,985.83 | 50.58% | 40.27% | Reference only |
| Remove the hidden warranty discount | 300,210.89 | 49.38% | 39.35% | $919.34 of unexplained discount on the analyser warranty line (`N170` in the workbook) |

> The 35% net-margin threshold is a demo assumption, tuned so the story works
> with the illustrative MiniMP prices. If you change those prices, re-run the
> scenarios and re-tune the threshold before rehearsal.

---

## 4. Findings: pain points to address in the demo

Each finding cites workbook evidence. Use them as the "today" contrast in the
talk track.

### 4.1 Process and data flow

| # | Finding | Evidence |
|---|---------|----------|
| P1 | **4+ re-keying loops.** The CSR builds the quote (step 7), "redoes the Margin Calculator to match" (9), re-enters it into Salesforce (10), modifies it to match the PO (13), enters the order into SAP (14), and Finance checks the calculator against SAP (16) | Overall Process rows 7–22 |
| P2 | **Margins are manually transcribed into Salesforce.** Approval runs against a file attachment, not live quote data | `N178`, `N190`; SFDC Instructions; Margin Sheet Instructions row 14 |
| P3 | **Revision control by file name.** "SFDC Opportunity Name Rev 0", and the calculator revision must equal the quote revision | Margin Sheet Instructions row 2; Overall Process C29 |
| P4 | **Two currency copies of the same logic.** The GBP sheet duplicates the LC sheet, and fixes get applied to one but not the other | Rev Log: Rev 4 and Rev 8 ("correction on … Pricing Sheet-GBP tab") |
| P5 | **Finance updates FX monthly** by hand in a hidden tab. Rate dated 2020-12-31, quote dated 2021-02-01 | Lookup Tables C15; Overall Process B4 |
| P6 | **SAP quote lines differ from internal lines.** Systems labour and 3rd-party costs fold into SAP line 31. SAP line 42 "Additional Project Management" actually carries Final Documentation ($1,500) | SAP Line Items F37, E124 |

### 4.2 Pricing governance

| # | Finding | Evidence |
|---|---------|----------|
| G1 | **Instructions contradict the formulas.** Systems: "60% Contribution Margin" vs. formula `/(1-0.4)` = 40%. Spares: "2% / 7% … 85% margin" vs. 5% / 15% at 80%. Packing: "0.5%" vs. 3% + $1,000. Freight: "2 × freight" vs. pass-through. Commissioning: "10% of Systems Value" vs. days × rate | Margin Sheet Instructions rows 7, 9–11 vs. `E43`, `E106:I107`, `J158`, `F161`, Service tab |
| G2 | **Pricing policy is hard-coded in formulas**: 0.4, 0.35, 0.05, 0.15, 0.2, 0.06, 0.03 + 1000, 4×450, 4×375, 5% contingency | `E43`, `E76`, `E106:E107`, `I106`, `F170`, `J158:J160`, `D174` |
| G3 | **Hidden discount**: 29.466% on the analyser warranty line, visible only as an 11.7% "warranty discount" on the Summary | `N170`; Summary F27/F46 |
| G4 | **"Costs cannot be revised by Sales"** is enforced only by cell protection | Overall Process C14, C27; Rev Log Rev 5 |
| G5 | **Discounts cascade invisibly.** Spares and packing derive from discounted systems value, so discounts are amplified (≈1.3×) | `E106` → `SAP Line Items!F37` |
| G6 | **Labour does not scale with quantity**: typed hour constants | `Systems Labour!H12 =4*16`, `M12/R12 =4*24` |
| G7 | **Broken controls**: dropdowns resolve to `#REF!`, and instructions reference cells that no longer exist (E2, D73, L55) | Data validation on `I206`, `I210:I211` |
| G8 | **Stale or inconsistent inputs are not validated.** Booking month May-2020 and delivery Oct-2020 on a Feb-2021 quote. "Credit Limit Adequate = No" only shows a note to forward to Credit Control | `I199:I201`, `I204`/`K204` |

### 4.3 Missed value

| # | Finding | Evidence |
|---|---------|----------|
| V1 | The **cash-flow** curve assumes a standard 6-month project and is overridden manually | Cash Flow A11–A14, `J200` |
| V2 | The **10-year installed-base potential** (£122K, including £89K service contracts) is guessed and never feeds a renewal or asset process | Install Base Rev |
| V3 | **Margin by category** (Summary) is only available as a static file, not reportable across deals | Summary |

---

## 5. Capability mapping: spreadsheet → Revenue Cloud

| Spreadsheet construct | Revenue Cloud capability | Demo treatment | Build status |
|-----------------------|--------------------------|----------------|--------------|
| Header (customer, opp, quote #, rev) | Opportunity → Quote, quote versioning | Live | Standard |
| Selling currency + region dropdown | Multi-currency quote, currency-specific price book entries; region as a quote field | Live | `CurrencyType` load pattern exists in the QB pricing plan (`qb-pricing`) |
| GBP Summary tab | Corporate-currency (GBP) converted amounts on quote and reports | Live (report) | Org setting |
| Analyser list price | Price Book Entry for the MiniMP base build, plus **attribute-based price adjustments** per option (`AttributeBasedAdjustment`) | Live: price follows options | **To build**: MiniMP 5200 base and option adjustments (§7.2) |
| Analyser configuration | Product Configurator + CML constraints | Live | **To build**: MiniMP 5200 attributes and constraints (§7.2). The `07930B1` NGL Lase 3 attributes ([manifest](../../datasets/sap/servomex-07930b1/manifest.yaml), [translation reference](../references/sap-vc-to-revenue-cloud-translation.md)) prove the SAP-to-attribute pipeline and can be reused for the MiniMP if Servomex provides its SAP VC class |
| Unit cost (typed) | **Cost Book / Cost Book Entry** | Live | Pattern exists in `qb-pricing`; **to build** Servomex entries |
| Systems cost-plus (cost / (1 − 40%)) | Pricing procedure formula step using an engineered cost entered by Systems/Proposals only | Live | **To build and validate** |
| Factored cost-plus (35%) | Same pricing procedure step, different target margin by product family | Narrate | To build (optional) |
| Labour rates by build location, service rates by region, annual uplifts | **Decision tables** in the pricing procedure (location/region → sell and cost rate) | Live: switch Houston → Shanghai | **To build** |
| Labour hours per system | Bundle components on `ASYSTEM` with quantity scaled per system | Live: fixes G6 | **To build** |
| Spares 5% / 15% of systems, warranty 6% × years | **Derived pricing** (`PricebookEntryDerivedPrice`) from the systems and analyser lines | Live: cascade | Pattern exists in `qb-pricing`; **to build** |
| Packing 3% + $1,000, docs, drawings | Auto-added expense lines priced by pricing-procedure formula | Live | **To build and validate** |
| Line discounts (column N) | Manual discount with field-level security; **Price Waterfall** | Live | Standard |
| "Costs cannot be revised by Sales" | Field-level security / permission sets per persona | Live | To configure |
| Contingency, agent commission, net margin | Quote-level calculated fields (decision table of commission % by product family) | Live | **Custom extension** to build |
| Margin approval by Finance, credit control, non-standard T&C | **Advanced Approvals** (`approvals` feature flag) with rules on net margin %, discount %, amount, credit, T&C | Live | Framework deployed by `prepare_approvals`; Servomex rules **to build** |
| Customer proposal PDF | **Document Generation** (`docgen` feature flag) with grouped lines | Live | Template **to build** |
| Category sections (Analysers / Systems / Spares / …) | Quote line groups | Live | To configure |
| SAP quote/order entry | Quote → Order; DRO orchestration (`dro` flag); SAP via integration | Narrate | Integration out of scope |
| Payment milestones 10/15/25/50 | Quote payment terms; Revenue Cloud Billing (`billing` flag) | Optional act | **Validate** milestone-billing support in the target release |
| Install Base Rev | Assets from the activated order; service and renewal opportunities | Optional act | Narrate |
| Cash Flow tab | Out of scope (ERP / project controls) | Do not demo | — |

> The `qb-pricing` plan loads `CostBook`, `CostBookEntry`,
> `PricebookEntryDerivedPrice`, `PriceAdjustmentSchedule`/`Tier`,
> `AttributeBasedAdjustment` and `BundleBasedAdjustment`. Reuse it as the
> structural pattern for a Servomex pricing plan. Do not reuse its QuantumBit
> data.

---

## 6. Recommended demo flow

The flow follows Servomex's **Overall Process** so each act replaces named
steps. Personas are Servomex's own roles.

| Act | Time | Persona | Replaces process step(s) | Key message |
|-----|-----:|---------|--------------------------|-------------|
| 0. Today | 3 min | Presenter | All | 14 tabs, 16 steps, 4+ re-keys, instructions that contradict formulas |
| 1. Opportunity → Quote | 4 min | Inside Sales / CSR | 1, 2, 7 | One record, with currency and region set once |
| 2. Configure analysers | 8 min | Inside Sales | 2 | MiniMP 5200 variants and options, constraint-checked and priced live from the catalog |
| 3. Engineered system + labour | 8 min | Systems / Proposals | 3, 4 | Cost-plus pricing, rate cards and labour that scales |
| 4. Auto-added value lines | 6 min | CSR | 5, 6 | Spares, service, warranty and expenses are added and priced by policy |
| 5. Sales discounting | 7 min | Sales | 8, 9 | Discount freely and see the margin impact live. Cost is read-only |
| 6. Approval | 6 min | Finance / Credit | 10, 15 | Rules route the quote, and approvers see the live margin breakdown |
| 7. Proposal | 3 min | CSR | 11 | Customer-ready PDF from the approved version |
| 8. PO change → Order | 5 min | CSR / Finance | 12, 13, 14, 16 | Revise and re-price; approvals re-evaluate on live data; then order |
| 9. *(optional)* Billing and installed base | 10 min | Finance / Service | Cash Flow, Install Base Rev | Milestone billing and an assets-based service pipeline |
| 10. *(optional)* Service upsell with the Quote Agent | 5 min | Service / Inside Sales | Service tab | One sentence to a priced Service Upsell quote: the agent creates the opportunity, the quote and the Service Day lines |

### Act 0 — "How it works today" (3 min)

- Open the workbook on `Pricing Sheet_LC`. Point at the blue input cells, the
  hard-coded `=I43/(1-0.4)`, and the "Use as … in Sales Force" labels on rows
  178 and 190.
- Show the *Overall Process* tab: 16 steps passed between Systems, Inside
  Sales, Service, CSR, Sales and Finance.
- **Talk track:** "71% of this $354K quote isn't priced from a price list. It's
  priced by formulas, and in five places the formulas don't match your own
  instructions. We'll quote the same deal in Revenue Cloud, with MiniMP 5200
  analysers in place of the 2700s."

### Act 1 — Opportunity to quote (4 min)

1. Open the LyondellBasell opportunity `[A2204] … CVO POSM1 2700 with SYSTEMS`.
2. Create a quote: currency **USD**, region **Americas**, Incoterms **FCA**, T&Cs
   **Servomex Standard**, expected booking month, and lead time **6 months**.
   Delivery date derives from these.
3. **Talk track:** Header data is entered once and drives rates, currency and
   approvals. No cell protection required.

### Act 2 — Configure the MiniMP 5200 (8 min)

1. Add 4 × **SERVOFLEX MiniMP 5200**. The configurator opens on **Standard
   Variant 01**: industrial O₂ paramagnetic cell, AFCD, single mA output, rear
   exhaust. List price is **$6,500** and cost **$1,600** (illustrative). Cost is
   visible only to permitted personas.
2. Show that power defaults to **US mains**, because the quote region is
   Americas.
3. Switch to **SV02**. The cell changes to high accuracy and the price rises
   by $1,200. Then switch to **User-configured** to unlock the full option set.
4. **Wow moment (constraints):**
   - With **AFCD** selected, the pump-only options are hidden: front exhaust,
     valved flowmeter and the sample conditioning panel. Change flow control to
     **internal pump** and they appear. The unvalved flowmeter, which is
     AFCD-only, disappears.
   - **Measurement 2** is available only on user-configured builds. Choose
     **IR CO₂**, and a **CO₂ range** attribute (10/25/50/100%) becomes required.
5. Finish the demo configuration:

   | Attribute | Value | List | Cost |
   |-----------|-------|-----:|-----:|
   | Base build | User-configured | 6,500 | 1,600 |
   | Measurement 1 | High-accuracy O₂ cell | +1,200 | +300 |
   | Measurement 2 | IR CO₂, 25% range | +2,400 | +600 |
   | Flow control | Internal pump with timer | +800 | +200 |
   | Power | Rechargeable battery, US | +900 | +250 |
   | Analogue output | Dual mA | +250 | +50 |
   | Sample conditioning | Panel with silica gel drier and catchpot | +650 | +175 |
   | Flowmeter | Valved, 1–10 l/min | +300 | +75 |
   | **Unit total** | | **13,000** | **3,250** |

6. Show the line: 4 × $13,000 = **$52,000**, cost **$13,000**, margin
   **75.0%**, calculated live. Open the price waterfall to show each option's
   attribute-based adjustment.
7. **Talk track:** The option matrix on your website, including every
   "pump version only" footnote, is now a rule in the configurator. Reps can't
   quote a combination the factory can't build, and the price follows the
   configuration without a lookup.

### Act 3 — Engineered system and labour (8 min)

1. Systems/Proposals persona adds 4 × `ASYSTEM` and enters an engineered unit
   cost of **$22,533.42**. Only this persona can edit cost.
2. The pricing procedure derives a list price of **$37,555.70** (40% target
   margin). Open the price waterfall to show the cost-plus step.
3. Expand the bundle: Engineering **16 h**, Electrical **24 h**, Piping **24 h**
   per system, priced from the Houston rate card ($173/$96 and $71/$55).
   Labour totals **$24,704 / $16,704 cost**.
4. **Wow moment:** change Build Location to **Shanghai**. Rates switch to the GBP
   rate card and convert to USD automatically. Switch back.
5. **Talk track:** Rate cards and annual uplifts move from a hidden tab into
   decision tables Finance maintains once. Hours scale with system quantity, so
   the `=4*16` problem disappears.

### Act 4 — Auto-added value lines (6 min)

1. Show the lines added automatically, grouped as **Spares / Service / Expenses
   / Warranty**:
   - Commissioning spares **$8,746.34** (5%) and 24-month spares **$26,239.02**
     (15%) of the systems + labour value; 4 × MiniMP 2-year spares kit @ $240
     (five filters and a filter-cap O-ring, per Servomex's recommended spares).
   - FAT and drift test (1 day each @ 8 h × $234), commissioning 3 days @
     $2,313, mobilisation $1,957.
   - Packing & handling **$9,265.36**, approval drawings $1,800, final
     documentation $1,500, all at cost.
   - Extended warranty 1 year @ 6% on analysers and on systems.
2. Show the quote totals: **$299,291.55**, CM **49.22%**, net **39.16%**. These
   match the workbook logic applied to the MiniMP deal (§3.2).
3. **Talk track:** "These lines are there to make you think of added value," as
   your own instructions say. Now policy adds them, and the policy is the one
   Finance approved, not one of five conflicting versions.

### Act 5 — Sales discounting with guardrails (7 min)

1. Switch to the Sales persona. Show cost fields are read-only. This replaces
   process step 8: "Costs cannot be revised by Sales".
2. Apply a **15% discount to systems**.
3. **Wow moment:** total drops by **$29,203**, not $22,533, because spares,
   packing and warranty re-derive. CM moves to **44.47%** and net to **34.41%**.
   The workbook amplifies this too, but nobody sees it.
4. Open the price waterfall on the analyser warranty line and show any manual
   discount, such as the **29.466%** buried in `N170` today. On this deal it
   hides **$919.34**.
5. **Talk track:** No more "finalize quote and redo Margin Calculator to match".
   The quote *is* the margin calculation.

### Act 6 — Approval (6 min)

1. Submit for approval. Use the demo rules below (assumptions to confirm with
   Servomex):

   | Rule | Approver | Fires in demo? |
   |------|----------|----------------|
   | Quote total > $125K / £75K / €75K (current threshold for completing the calculator) | Finance margin review | Yes |
   | Net margin < 35% | Finance / Project Controls | Yes (34.41%) |
   | Any line discount > 10% | Sales Manager | Yes (15% systems) |
   | Credit limit adequate = No | Credit Control | Yes |
   | T&Cs ≠ Servomex Standard | Legal / Commercial | No |

2. As the Finance approver, show the approval record with the **margin by
   category** (the Summary tab, live), GBP-converted totals, and the discount
   that triggered the rule.
3. Approve. Show that a later change that stays inside the thresholds does not
   re-trigger approval.

### Act 7 — Proposal (3 min)

1. Generate the customer proposal with Document Generation. Show grouped
   sections, payment milestones (10/15/25/50), Incoterms and T&Cs.
2. **Talk track:** The quote version is the revision. No more `… Rev 2.xlsx`
   saved under the opportunity.

### Act 8 — PO change to order (5 min)

1. The customer PO is for **3 systems**. Revise the approved quote and set the
   system quantity to 3, keeping the 15% systems discount.
2. Labour, spares, warranty and packing re-derive. Totals are **$221,083.35**,
   CM 46.36%, net **36.03%**.
3. Resubmit. The approval rules re-evaluate on live data. The net-margin rule
   no longer fires, so the Finance margin step drops out. The discount and
   credit rules still route to their approvers.
4. Contrast: the workbook would leave labour at 4 systems' hours and
   overstate the quote by **$7,634**.
5. Create the order from the accepted quote. Show the DRO orchestration plan
   and narrate the SAP order hand-off. This replaces steps 14 and 16.

### Act 9 — *(optional)* Billing and installed base (10 min)

- Billing: milestone schedule from payment terms (10% order, 15% drawings, 25%
  FAT, 50% shipment). Only demo this once milestone billing is validated in the
  target org. Otherwise show the payment terms on the quote and order.
- Installed base: assets created from the order, with a service-contract
  opportunity seeded from them. This replaces the guessed £89K "Service
  Contract/year" in *Install Base Rev*.

### Act 10 — *(optional)* Service upsell with the Quote Agent (5 min)

A **Service Upsell** for **Lonza Biologics UK Ltd**, a customer that already
owns Servomex analysers. The rep quotes **Training** and a **Site Acceptance
Test (SAT)** by the **Service Day** in one sentence to the **Servomex Quote
Agent**. The act stands alone: it doesn't need Acts 1–9.

**One-time setup** (before rehearsal; take the shared org lock for each step):

1. Load the `servomex-services` data plan from rlm-base-dev. It adds
   *Operator Training — per Service Day* (`SMX-SVC-TRN-DAY`) and *Site
   Acceptance Test (SAT) — per Service Day* (`SMX-SVC-SAT`), each at
   **£1,606.80** per Service Day in GBP:
   `cci task run load_sfdmu_data --org servomex -o pathtoexportjson <servomex repo>/TBD(#58): servomex-services export.json path from #55`.
2. Rebuild the product catalog search index, so the agent can find both
   products: `TBD(#58): index rebuild step from the servomex-services README (#55)`.
3. Deploy, publish and activate the Servomex Quote Agent
   (`SMX_Revenue_Quote_Management`) with rlm-base-dev's `deploy_agents`,
   `publish_agents` and `activate_agents`: `TBD(#58): exact commands and options from #56/#57`.
4. Assign `SMX_QuotingAgent` to every user who holds `RLM_QuotingAgent`
   (`TBD(#58): command from #56`). Then, **only once the agent has passed its
   agent test (#57)**, remove `RLM_QuotingAgent` from the presenter, so their
   agent panel offers only the Servomex Quote Agent. The script changes no
   other user, and refuses to run unless the presenter holds
   `SMX_QuotingAgent`:
   `sf apex run --file scripts/apex/removePresenterTemplateQuotingAgent.apex --target-org <sf-alias>`.
5. Set Lonza's account currency to GBP, so a new opportunity for it quotes
   in GBP. The script is re-runnable, and Lonza's existing USD opportunities
   keep their currency:
   `sf apex run --file scripts/apex/setLonzaAccountCurrencyToGbp.apex --target-org <sf-alias>`.

**Run the act:**

1. Open the **Lonza Biologics UK Ltd** account as the presenter. Open the
   agent panel and pick `TBD(#58): agent label as shown in the panel`. Don't
   start from one of Lonza's opportunities: on an opportunity page, the
   agent quotes that opportunity instead of creating one.
2. Type:

   > Create a services quote for Lonza Biologics UK Ltd in GBP with 2 operator training days and 1 SAT day.

3. The agent proposes a new opportunity and asks for one confirmation. Check
   the proposal against the defaults:

   | Field | Expected |
   |-------|----------|
   | Name | Lonza Biologics UK Ltd — Services — ‹today, YYYY-MM-DD› |
   | Stage | Proposal/Quote |
   | Close date | Today + 30 days |
   | Currency | GBP |
   | Price book | Standard Price Book |

   `TBD(#58): the agent's confirmation wording from #57`.
4. Confirm:

   > Yes, create it.

5. The agent creates the opportunity (Next Step *Send services quote*) and
   its quote, adds the lines, and replies with the lines, the total and
   links to both records:

   | Line | Service Days | Unit price | Line total |
   |------|-------------:|-----------:|-----------:|
   | Operator Training — per Service Day (`SMX-SVC-TRN-DAY`) | 2 | £1,606.80 | £3,213.60 |
   | Site Acceptance Test (SAT) — per Service Day (`SMX-SVC-SAT`) | 1 | £1,606.80 | £1,606.80 |
   | **Total** | | | **£4,820.40** |

6. Open the quote from the link and show the same two lines and total.

**If it goes wrong:**

- A line priced in USD, or no price, means the quote isn't in GBP. Check
  Lonza's currency (setup step 5).
- If the agent lists several products for "training", pick *Operator
  Training — per Service Day*. The 2-day package `SMX-SVC-TRN` is a
  different product.
- Don't name one of Lonza's existing opportunities. They are USD, and the
  service products have GBP prices only.
- Every rehearsal adds a new Lonza opportunity. That's by design: each
  Service Upsell is its own deal.

**Talk track:** In the workbook, Service is one more tab of day rates by
region, re-keyed into every quote. Here the Service Day rate is a catalog
price, and the agent builds the whole quote, opportunity included, from one
sentence. The same motion applies to LyondellBasell: once its order is
activated and the MiniMP analysers are its installed base (Act 9), the rep
quotes their Training and SAT the same way.

---

## 7. Demo data build sheet

Values come from the reference deal, except the MiniMP 5200 lines, which use
illustrative prices. Build in the demo org before rehearsal.

### 7.1 Products and price book (USD)

| SKU / product | Type | List price | Unit cost | Notes |
|---------------|------|-----------:|----------:|-------|
| SERVOFLEX MiniMP 5200 | Configurable (§7.2) | 6,500.00 base + option adjustments | 1,600.00 base + option costs | **Illustrative.** The demo configuration is $13,000 / $3,250 per unit |
| `ASYSTEM` Analyser System | Bundle | Cost-plus 40% | Engineered (deal input) | Components below |
| Systems Engineering Hour | Bundle component | Rate card | Rate card | 16 h per system |
| Systems Electrical Hour | Bundle component | Rate card | Rate card | 24 h per system |
| Systems Piping Hour | Bundle component | Rate card | Rate card | 24 h per system |
| Commissioning Spares | Derived | 5% of systems + labour | 20% of price | |
| 24 Month Spares | Derived | 15% of systems + labour | 20% of price | |
| MiniMP 2-year spares kit | Simple | 240.00 | 60.00 | **Illustrative.** Five replacement filters and a filter-cap O-ring. One per analyser |
| FAT Day / Drift Test Day | Service | 8 h × hourly rate | 8 h × cost rate | Americas $234 / $68 |
| Commissioning Day | Service | Daily rate | Daily cost | Americas $2,313 / $549 |
| Mobilisation | Service | 1,957.00 | 549.00 | Typed in the workbook (`Service!I26`) |
| Packing & Handling | Expense | 3% × (material + labour + service) + 1,000 | = price | |
| Approval Drawings | Expense | 450 / drawing | = price | 4 drawings |
| Final Documentation | Expense | 375 / document | = price | 4 documents |
| Extended Warranty — Analysers | Derived | 6% × years × analyser sell | 15% of list | |
| Extended Warranty — Systems | Derived | 6% × years × systems sell | 15% of list | |

### 7.2 MiniMP 5200 attribute model

Options come from the variant comparison on the
[MiniMP 5200 product page](https://www.servomex.com/gas-analyzers/finder/minimp-5200/).
That page's per-variant availability ticks didn't survive text extraction, so
the group names and the AFCD/pump split below are read from its labels and
footnotes. Confirm them against the brochure, the operator manual or the SAP VC
class before building.

| Attribute | Values | Default |
|-----------|--------|---------|
| Variant | SV01, SV02, SV03, SV04, User-configured | SV01 |
| Measurement 1 | Industrial O₂ PM cell (±0.1%), High-accuracy O₂ PM cell (±0.05%), IR CO₂ | Industrial O₂ |
| Measurement 2 | None, Industrial O₂ PM cell, High-accuracy O₂ PM cell, IR CO₂ | None |
| CO₂ range | 10%, 25%, 50%, 100% | — |
| Flow control | AFCD (1–10 psig inlet), Internal pump 0.7 l/min with timer | AFCD |
| Power | UK mains, US mains, European mains, Rechargeable battery UK, US or European | From quote region |
| Analogue output | None, Single mA, Dual mA | Single mA |
| Sample inlet | QuickConnect barb for 1/4" ID tube, 1/8" NPT adaptor | Barb |
| Exhaust | Rear, Front | Rear |
| Flowmeter | None, Unvalved 1–10 l/min, Valved 1–10 l/min | None |
| Sample conditioning panel | No, Yes (silica gel drier and catchpot) | No |
| Sample probe | None, 25 cm 316 SS tip (<180 °C), 1 m 316 SS | None |
| Display language | English, French, German, Italian | English |

**Constraints (CML)**

| # | Rule | Source |
|---|------|--------|
| C1 | SV01 = industrial O₂ + AFCD. SV02 = high-accuracy O₂ + AFCD. SV03 = industrial O₂ + pump. SV04 = high-accuracy O₂ + pump. Every standard variant fixes single mA output and rear exhaust | Variant descriptions |
| C2 | Measurement 2 ≠ None only when Variant = User-configured. A dual build is one O₂ cell plus IR CO₂ | "Can have two measurements — Industrial or high accuracy O₂ and 10%, 25%, 50%, 100% CO₂" |
| C3 | CO₂ range is required when either measurement is IR CO₂, and hidden otherwise | Same |
| C4 | Exhaust = Front requires Flow control = Pump | "Front (pump version only)" |
| C5 | Flowmeter = Valved requires Pump. Flowmeter = Unvalved requires AFCD | "(pump version only)", "(AFCD only)" |
| C6 | Sample conditioning panel = Yes requires Pump | "(pump version only)" |
| C7 | Power defaults to the plug type for the quote region, for example Americas → US mains | Demo convenience, not a product rule |

**Attribute-based price adjustments (illustrative, USD)**

| Option | List | Cost |
|--------|-----:|-----:|
| Base build (SV01 content) | 6,500 | 1,600 |
| High-accuracy O₂ cell | +1,200 | +300 |
| IR CO₂ as Measurement 2 | +2,400 | +600 |
| IR CO₂ as Measurement 1 (replaces the O₂ cell) | +1,200 | +300 |
| Internal pump | +800 | +200 |
| Rechargeable battery | +900 | +250 |
| Dual mA output | +250 | +50 |
| Sample conditioning panel | +650 | +175 |
| Valved flowmeter | +300 | +75 |
| Unvalved flowmeter | +250 | +60 |
| 1/8" NPT adaptor | +60 | +15 |
| Probe, 25 cm / 1 m | +350 / +450 | +90 / +120 |

With these, the standard variants list at SV01 $6,500, SV02 $7,700, SV03
$7,300 and SV04 $8,500.

> **Cost per option needs a design decision.** Cost Book entries are per
> product, not per attribute. Either model the costed options as child
> components of a MiniMP bundle, or add a pricing-procedure step that derives
> cost from the selected attributes. Validate the chosen approach before
> rehearsal.

### 7.3 Decision tables

| Table | Key | Outputs | Rows (2021 rates) |
|-------|-----|---------|-------------------|
| Systems Labour Rate | Build location | Currency, Eng sell/cost, Mfg sell/cost | Houston USD 173/96, 71/55 · Shanghai GBP 53/26, 32/11 · Europe GBP 57/31 · Singapore GBP 47/24 |
| Service Labour Rate | Service region | Currency, in-house hourly sell/cost, site daily sell/cost | Americas USD 234/68, 2,313/549 · UK GBP 131/45, 1,607/361 · Europe/ME EUR 158/51, 1,928/404 · Korea/Japan USD 154/43, 1,333/343 · Singapore USD 154/43, 1,076/343 · Rest of Asia USD 154/43, 1,230/341 · ANZ USD 154/43, 1,333/341 · China RMB 615/168, 8,798/1,345 |
| Cost-plus Target Margin | Product family | Target margin % | Systems 40% · Factored 35% · 3rd-party 40% |
| Agent Commission | Product family | Commission % | Analysers 15% · Systems 10% · Factored 0% · Spares 15% · Service 15% |

### 7.4 Currencies

GBP corporate. USD 1.3652, EUR 1.1119, RMB 8.9205 and INR 99.756 per GBP, as
at 2020-12-31 (Lookup Tables). Refresh to current rates for the demo.

---

## 8. Risks and things to avoid

- **Don't promise native commission or contingency.** Revenue Cloud prices and
  costs lines. Agent commission and the 5% cost-only contingency need quote-level
  custom calculation. Present them as configured, not out-of-the-box.
- **Validate before rehearsal:** cost-plus pricing from a per-deal engineered
  cost; derived pricing from a bundle total (systems + labour); and packing as
  a percentage of the quote subtotal plus a fixed fee. If any can't be done
  declaratively in time, pre-price that line and narrate the rule.
- **Don't demo the Cash Flow tab.** It belongs to ERP and project controls.
- **Don't reproduce the workbook's defects.** Ask Servomex which policy is
  correct where instructions and formulas disagree (G1), and whether the
  warranty discount (G3) was intentional. Then demo the corrected policy and say
  so.
- **Use customer data with care.** The workbook names a real customer.
  Confirm with Servomex that using the LyondellBasell deal in the demo is
  acceptable. Otherwise anonymise the account and keep the numbers.
- **MiniMP prices are illustrative.** Servomex doesn't publish them. Label them
  as such on screen, or replace them with real prices and re-run §3.2–§3.3 and
  the approval threshold before rehearsal.
- **Product fit.** The MiniMP 5200 is a portable, safe-area analyser for clean,
  dry, non-flammable, non-toxic samples. In a petrochemical systems project it
  is plausible as a portable reference or verification analyser, not as the
  in-line process analyser the original `02700D1` lines were. Expect the
  question, and say the deal was adapted for the demo.

## 9. Open questions for Servomex

1. Which list-price rules are current: the formulas (40% systems, 5%/15% spares,
   3% + $1,000 packing) or the instructions (60%, 2%/7%, 0.5%)?
2. What are the actual approval thresholds (margin %, discount %, amount) and
   approvers by region? Today's only explicit rule is the >$125K / £75K / €75K
   requirement to complete the calculator.
3. Should approvals use contribution margin, net margin, or both?
4. Is the MiniMP 5200 configured through a SAP VC class like `07930B1`? If so,
   can we have the class document, so its options and rules can be migrated
   with the existing [SAP attribute migration](../../datasets/sap/servomex-07930b1/manifest.yaml)
   approach instead of being read from the website?
5. What are the real MiniMP 5200 list prices and standard costs for the base
   build and each option?
6. Is the 29.466% warranty discount on `N170` a standard concession or a
   one-off?
7. Are Europe and Asia in scope? The process tab says "Process investigation
   necessary for Europe & Asia".
8. Should the installed-base forecast become service and renewal opportunities
   in Salesforce?
