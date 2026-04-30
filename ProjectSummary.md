# PropScore: 10-Minute Hackathon Demo & Pitch Script

**Objective:** Pitch the PropScore platform to the judges by demonstrating the working prototype while continually anchoring the logic back against your Production Architecture Diagram. The tone should be confident, technical but accessible, and emphasize why this is *decision-ready intelligence*, not just another price-estimator.

---

### Phase 1: The Pitch & The Problem (0:00 – 1:30)

**What to show:** 
Start on the PropScore `LandingHub` screen. 

**What to say:**
*"Today, collateral-backed lending suffers from a massive trust deficit. Lenders and underwriters rely on slow manual appraisals because digital valuation tools simply spit out a price—they don't tell the underwriter whether the data is actually believable, how liquid the asset is, or how confident the system is in its own estimate.*

*That's where PropScore comes in. We’ve built a 15-layer deterministic collateral intelligence pipeline. Our platform doesn't just evaluate price; it processes collateral in layers—from intake normalization, to live geospatial verification, to anomaly detection, and finally, confidence adjustment.*

*Right now, I’ll run a live property case through our engine. Then, I'll show you the exact production architecture behind how an enterprise bank would deploy this."*

---

### Phase 2: Live Intake & Normalization (1:30 – 3:00)

**What to do / click:** 
1. Click **"Enter the Application"** to launch the `InputWizard`.
2. Type address: **"Hiranandani Powai, Mumbai"** or **"NRI Complex, Seawoods"** (a case you know triggers interesting anomalies!).
3. Move to Step 2: Ensure Type is "Apartment", but set Area to a highly anomalous number like **200 sqft**.
4. Click **"Generate Intelligence"**.

**What to say during the Input Flow:**
*"The moment data enters our system, we don't just blindly trust it. Our **Intake Resolution** engine first normalizes everything. If a user types in 'sq meters' or a vague property sub-type, we use fuzzy taxonomy matching to map it directly to fixed internal underwriting classes. You can see our data-completeness schema aggressively validating the inputs.* 

*(As you click 'Generate Intelligence' and the terminal pops up)*:
*Once submitted, the case is handed over to our **Agentic Swarm Orchestrator**. What you are seeing here isn't a loading screen—these are independent asynchronous AI agents processing the matrix in real-time. The Vision Agent, the Geospatial Agent, and the Legal Agent are working in parallel to build localized context."*

---

### Phase 3: Verification & Anomaly Engine (3:00 – 5:00)

**What to show:** 
Wait for the Dashboard to load. Immediately focus on the top **Verification Engine Output** banner and the **Suspicion Score**.

**What to say:**
*"This is where PropScore completely separates itself from standard valuation tools. Before we give you a price, we give an absolute Verification Decision. Because I entered a 200 sqft apartment in Powai, the **Anomaly Engine** instantly flagged it.*

*(Point to the Identified Deficits & Anomalies panel)*
*Our mathematical engine cross-referenced my input against Micro-Market norms. It realized 200 sqft is well below the 5th percentile for this specific locality and automatically threw a 'Size-Config Mismatch' critical flag. It also bumped up our **Suspicion Score**.* 

*(Hover over the XAI Bubbles / Question marks next to the metrics)*
*We’ve also embedded these glassmorphic **Explainable AI (XAI)** portals directly into the UI. Underwriters don't like 'black boxes'. If they want to know exactly how the Suspicion Score was derived, or why the Data Sufficiency score is low, they just hover here. It exposes the underlying mathematical heuristics, building immense psychological trust in the software."*

---

### Phase 4: Geospatial & Liquidity Intelligence (5:00 – 7:00)

**What to show:** 
Scroll down to the **Geospatial Reconnaissance Map** and toggle the **Impact Factors**. 

**What to say:**
*"A property's value isn't just about its walls. It's about its literal connection to the city. During the Agent Swarm phase, our Engine reached out to the live OpenStreetMap Overpass API, pulled the true coordinates, and physically mapped the infrastructure radius.*

*(Point to the map markers)*
*Notice how it automatically locates and calculates the Haversine distance to the nearest Metro lines, hospitals, and commercial hubs? The system then classifies these as **positive or negative yield impact factors**. This generates our Resale Liquidity Index—telling the bank not just the Distress Sale Value, but exactly how many days it will take to liquidate the asset if the borrower defaults."*

---

### Phase 5: The Production Architecture (7:00 – 9:00)

**What to show:** 
Alt-tab to your **Production Architecture Diagram**. Leave it on screen up for the full 2 minutes so judges can digest it.

**What to say:**
*"Everything you just saw was executing on our real frontend framework using deterministic fallbacks and live API calls. But let me show you how this scales at an enterprise level.*

*(Point to the Middle 'API Gateway / Case Orchestrator')*
*In a production environment, loans flow through the API Gateway, and hit our Stage 1 Normalization Service. From there they jump to the **Location & Bucket Assignment Service**.*

*(Point to the external Green connectors on the right)*
*The beauty of this architecture is its modularity. The OpenStreetMap API I just showed you plugs right in here, alongside live Government Circle-Rate feeds and public listing APIs.* 

*(Point to the bottom 'Core Intelligence & Scoring Layer')*
*All the localized anomalies and Suspicion Scores you saw in the dashboard? That math executes right here in the Core Intelligence Layer, pulling from dedicated Market Norms databases. This ensures the engine evaluates risk not against national averages, but against hyper-localized, offline data pipelines that ensure sub-second latency.*

*(Point to the Historical Reliability Service)*
*We can even run a **Historical Reliability Service** that backtests the current valuation against previous defaults from the bank's own ledger to further penalize or reward the confidence score."*

---

### Phase 6: Conclusion (9:00 – 10:00)

**What to show:** 
Alt-tab back to the **PropScore Dashboard**. 

**What to say:**
*"By weaving location intelligence, autonomous anomaly verification, and Explainable AI into a single workflow, PropScore shifts collateral assessment from subjective guesswork into an audited, deterministic science. We don’t just estimate property value. We calculate exact liquidity risk, empowering lenders to make safer, radically faster underwriting decisions.*

*Thank you, and I look forward to your questions."*
