"use client";

import { useState } from "react";

const demos = [
  { model: "Genie 3", org: "Google DeepMind", caseId: "GC004", family: "Geometry Consistency", duration: "71.2s", src: "/demos/genie3-gc004.mp4", poster: "/posters/genie3-gc004.jpg", prompt: "Move right 10 steps, then return to the original position." },
  { model: "HYWorld2", org: "Tencent", caseId: "OE010", family: "Insight Evolution", duration: "60.9s", src: "/demos/hyworld2-oe010.mp4", poster: "/posters/hyworld2-oe010.jpg", prompt: "Wait and observe the world as it evolves." },
  { model: "HappyOyster", org: "Alibaba", caseId: "GC016", family: "Geometry Consistency", duration: "60.1s", src: "/demos/happyoyster-gc016.mp4", poster: "/posters/happyoyster-gc016.jpg", prompt: "Walk to the ancient pagoda, then look upward at the tower." },
  { model: "LingBot-World", org: "Ant Group", caseId: "OE005", family: "Insight Evolution", duration: "60.0s", src: "/demos/lingbot-world-oe005.mp4", poster: "/posters/lingbot-world-oe005.jpg", prompt: "Wait and observe continuous scene evolution." },
  { model: "LingBot-World Infinity", org: "Ant Group", caseId: "GC004", family: "Geometry Consistency", duration: "40.0s", src: "/demos/lingbot-infinity-gc004.mp4", poster: "/posters/lingbot-infinity-gc004.jpg", prompt: "Move right 10 steps, then return to the original position." },
  { model: "SANA-WM", org: "NVIDIA", caseId: "OE070", family: "Out-of-sight Evolution", duration: "33.0s", src: "/demos/sana-wm-oe070.mp4", poster: "/posters/sana-wm-oe070.jpg", prompt: "Turn left 180°, then return to the original view." },
  { model: "GameCraft 2", org: "Tencent", caseId: "OE001", family: "Insight Evolution", duration: "41.3s", src: "/demos/gamecraft2-oe001.mp4", poster: "/posters/gamecraft2-oe001.jpg", prompt: "Wait and observe the visible world evolve." },
  { model: "Hunyuan WorldPlay", org: "Tencent", caseId: "OE033", family: "Insight Evolution", duration: "40.8s", src: "/demos/hunyuan-worldplay-oe033.mp4", poster: "/posters/hunyuan-worldplay-oe033.jpg", prompt: "Slowly move the camera to the right." },
  { model: "Matrix-Game 3", org: "Skywork AI", caseId: "OE030", family: "Out-of-sight Evolution", duration: "33.5s", src: "/demos/matrixgame3-oe030.mp4", poster: "/posters/matrixgame3-oe030.jpg", prompt: "Follow the silver SUV down the spiral ramp, then tilt back up." },
];

const findings = [
  { title: "Geometry Consistency", leader: "Genie 3", color: "cyan", note: "Identity, texture, color and spatial layout under viewpoint change." },
  { title: "Interaction Fidelity", leader: "Genie 3", color: "coral", note: "Contact, support, kinematics, causality and solid boundaries." },
  { title: "Insight Evolution", leader: "Genie 3", color: "violet", note: "Continuously visible worlds must accumulate meaningful, causal change." },
  { title: "Out-of-sight Evolution", leader: "Genie 3", color: "gold", note: "Hidden state must progress and reappear without reset or contradiction." },
];

export default function Home() {
  const [activeIndex, setActiveIndex] = useState(0);
  const active = demos[activeIndex];
  const step = (delta: number) => setActiveIndex((activeIndex + delta + demos.length) % demos.length);

  return (
    <main>
      <nav className="nav" aria-label="Main navigation">
        <a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a>
        <div className="nav-links">
          <a href="#overview">Overview</a><a href="#method">Method</a><a href="#paper">Paper Figures</a><a href="#demos">Demos</a><a href="#findings">Findings</a>
        </div>
        <a className="nav-cta" href="#demos">Explore demos <span>↘</span></a>
      </nav>

      <section className="hero" id="top">
        <div className="ambient ambient-one"/><div className="ambient ambient-two"/>
        <div className="eyebrow"><span className="pulse"/> PLAYER-GUIDED EVALUATION FOR INTERACTIVE WORLD MODELS</div>
        <h1>Can a generated world<br/><em>remember, respond, and evolve?</em></h1>
        <p className="hero-copy">PlayWorld evaluates long-horizon interactive worlds through adaptive play—not isolated frames. It reveals when geometry drifts, interactions break, and off-screen states quietly reset.</p>
        <div className="hero-actions"><a className="button primary" href="#demos">Watch model rollouts <span>▶</span></a><a className="button ghost" href="#method">See how it works <span>↓</span></a></div>
        <div className="metric-row">
          <div><strong>171</strong><span>benchmark cases</span></div>
          <div><strong>1,417</strong><span>interactive videos</span></div>
          <div><strong>30–60s</strong><span>long-horizon rollouts</span></div>
          <div><strong>4</strong><span>diagnostic task families</span></div>
        </div>
        <div className="hero-stage" aria-hidden="true">
          <div className="orbit orbit-a"/><div className="orbit orbit-b"/>
          <div className="world-card world-card-a"><img src="/figures/gc001.jpg" alt=""/><span>REVISIT</span></div>
          <div className="world-card world-card-b"><img src="/figures/if001.png" alt=""/><span>INTERACT</span></div>
          <div className="world-card world-card-c"><img src="/figures/oe001.jpg" alt=""/><span>EVOLVE</span></div>
          <div className="player-node"><small>VISUAL CONTROL AGENT</small><b>PLAYER</b><span>observes · decides · adapts</span></div>
        </div>
      </section>

      <section className="section intro" id="overview">
        <div className="section-kicker">01 / THE QUESTION</div>
        <div className="intro-grid"><h2>Beautiful frames are easy.<br/><span>Persistent worlds are not.</span></h2><div><p>Existing evaluations often collapse an interactive rollout into visual quality or endpoint success. PlayWorld follows the complete trajectory and asks whether early world states survive later actions.</p><p>It separates control complexity from temporal state dependency: even a single wait or rotation can demand long-range memory, causal evolution, and consistent re-observation.</p></div></div>
      </section>

      <section className="section method" id="method">
        <div className="section-kicker light">02 / WHAT WE EVALUATE</div>
        <div className="section-head light-head"><h2>Four ways to test a world.</h2><p>A capability-specific checklist turns each rollout into localized, traceable evidence.</p></div>
        <div className="pillar-grid">
          <article className="pillar cyan"><span className="pillar-number">01</span><div className="pillar-symbol">⌁</div><h3>Geometry<br/>Consistency</h3><p>Does the same world survive motion and revisit?</p><ul><li>Identity & object count</li><li>Material & color stability</li><li>Relative 3D layout</li><li>Closed-loop return views</li></ul><b>48 cases · GC</b></article>
          <article className="pillar coral"><span className="pillar-number">02</span><div className="pillar-symbol">↯</div><h3>Interaction<br/>Fidelity</h3><p>Do actions cause coherent physical responses?</p><ul><li>Contact & support</li><li>Causal response</li><li>Motion kinematics</li><li>Collision boundaries</li></ul><b>50 cases · IF</b></article>
          <article className="pillar violet"><span className="pillar-number">03</span><div className="pillar-symbol">◌</div><h3>Insight<br/>Evolution</h3><p>Does a visible process keep making meaningful progress?</p><ul><li>Continuous progression</li><li>Prompt alignment</li><li>Identity preservation</li><li>Physical causality</li></ul><b>30 cases · IE</b></article>
          <article className="pillar gold"><span className="pillar-number">04</span><div className="pillar-symbol">↻</div><h3>Out-of-sight<br/>Evolution</h3><p>Does hidden state continue evolving beyond the current view?</p><ul><li>Hidden-state progression</li><li>Revealed-state difference</li><li>Trajectory continuity</li><li>No reset on reveal</li></ul><b>43 cases · OE</b></article>
        </div>
      </section>

      <section className="section engine">
        <div className="section-kicker">03 / HOW WE EVALUATE</div>
        <div className="section-head"><h2>A player in the loop.</h2><p>PlayWorldEngine runs the model, executes structured actions, and records complete interaction evidence. The Player observes intermediate frames and decides whether to keep, stop, or extend.</p></div>
        <div className="flow" id="suite">
          <div className="flow-node"><span>01</span><b>Task-conditioned<br/>action sequence</b><small>Prompt · first frame · controls</small></div><div className="flow-arrow">→</div>
          <div className="flow-node featured"><span>02</span><b>PlayWorldEngine</b><small>Live session · timed actions · capture</small></div><div className="flow-loop"><strong>PLAYER</strong><i>↕</i><small>adaptive decisions</small></div>
          <div className="flow-arrow">→</div><div className="flow-node"><span>03</span><b>Interactive<br/>world model</b><small>Frames · state · response</small></div><div className="flow-arrow">→</div>
          <div className="flow-node"><span>04</span><b>Evidence-grounded<br/>VQA</b><small>4–7 case-specific checks</small></div>
        </div>
        <div className="suite-strip"><span>171 CASES</span><span>48 GC</span><span>50 IF</span><span>30 INSIGHT</span><span>43 OUT-OF-SIGHT</span><span>797 APPLICABLE QUESTIONS</span></div>
      </section>

      <section className="section paper-evidence" id="paper">
        <div className="section-kicker">04 / FROM THE PAPER</div>
        <div className="section-head"><h2>Grounded in real trajectories,<br/>not illustrative stand-ins.</h2><p>Selected figures from the paper show the benchmark design, data construction, and representative failure evidence. Only three are included here to keep the story focused.</p></div>
        <figure className="paper-hero"><img src="/figures/paper-teaser.jpg" alt="PlayWorld paper overview showing four evaluation families, the player-guided engine, and model ranking snapshots"/><figcaption>Paper overview: what PlayWorld evaluates, how the adaptive player controls rollouts, and the resulting capability rankings.</figcaption></figure>
        <div className="paper-pair">
          <figure><img src="/figures/paper-data-construction.jpg" alt="PlayWorld dataset construction pipeline from initial world settings through objectives, actions, and structured VQA questions"/><figcaption>Data construction pipeline: real starting worlds, long-horizon objectives, executable controls, and structured VQA.</figcaption></figure>
          <figure><img src="/figures/paper-qualitative.jpg" alt="Qualitative PlayWorld failure cases across interaction, geometry, insight, and out-of-sight evolution"/><figcaption>Qualitative evidence: localized failures in interaction, geometry, visible evolution, and hidden-state evolution.</figcaption></figure>
        </div>
        <div className="paper-table-wrap">
          <div><small>BENCHMARK COMPOSITION</small><h3>Four task families, four distinct temporal demands.</h3><p>The split follows the paper taxonomy; Insight and Out-of-sight Evolution are evaluated separately rather than merged into one generic evolution score.</p></div>
          <table><thead><tr><th>Task family</th><th>Cases</th><th>Primary temporal test</th></tr></thead><tbody>
            <tr><td><span className="dot cyan-dot"/>Geometry Consistency</td><td>48</td><td>Revisit and loop closure</td></tr>
            <tr><td><span className="dot coral-dot"/>Interaction Fidelity</td><td>50</td><td>Approach, contact, response</td></tr>
            <tr><td><span className="dot violet-dot"/>Insight Evolution</td><td>30</td><td>Continuous visible progression</td></tr>
            <tr><td><span className="dot gold-dot"/>Out-of-sight Evolution</td><td>43</td><td>Hidden progression and reveal</td></tr>
          </tbody><tfoot><tr><td>Total</td><td>171</td><td>30–60 s rollouts</td></tr></tfoot></table>
        </div>
      </section>

      <section className="section demos" id="demos">
        <div className="section-kicker">05 / CURATED MODEL ROLLOUTS</div>
        <div className="section-head"><h2>One long-horizon case.<br/>Every evaluated model.</h2><p>Nine representative rollouts, each longer than 30 seconds. Switch models without leaving the trajectory.</p></div>
        <div className="demo-shell">
          <div className="video-wrap">
            <video key={active.src} controls playsInline preload="metadata" poster={active.poster} onEnded={() => step(1)}><source src={active.src} type="video/mp4"/>Your browser does not support video playback.</video>
            <div className="video-badges"><span>{active.family}</span><span>{active.duration}</span></div>
          </div>
          <aside className="demo-info">
            <div className="demo-index">{String(activeIndex + 1).padStart(2,"0")} <span>/ {String(demos.length).padStart(2,"0")}</span></div>
            <div><small>MODEL · {active.org}</small><h3>{active.model}</h3></div>
            <div className="case-meta"><span>CASE</span><b>{active.caseId}</b><span>TASK FAMILY</span><b>{active.family}</b></div>
            <blockquote>“{active.prompt}”</blockquote>
            <div className="demo-controls"><button onClick={() => step(-1)} aria-label="Previous model">←</button><div className="progress"><i style={{width:`${((activeIndex + 1) / demos.length) * 100}%`}}/></div><button onClick={() => step(1)} aria-label="Next model">→</button></div>
          </aside>
        </div>
        <div className="model-tabs" role="tablist" aria-label="Choose a model">{demos.map((demo,index)=><button key={demo.model} className={index===activeIndex?"active":""} onClick={()=>setActiveIndex(index)} role="tab" aria-selected={index===activeIndex}><span>{String(index+1).padStart(2,"0")}</span>{demo.model}</button>)}</div>
      </section>

      <section className="section findings" id="findings">
        <div className="section-kicker light">06 / WHAT WE FIND</div>
        <div className="section-head light-head"><h2>Capability must be read<br/>one family at a time.</h2><p>The paper reports separate rankings for Geometry, Interaction, Insight Evolution, and Out-of-sight Evolution.</p></div>
        <div className="finding-grid">{findings.map((item,index)=><article className={`finding ${item.color}`} key={item.title}><span>0{index+1}</span><h3>{item.title}</h3><p>{item.note}</p><div><small>PAPER SNAPSHOT LEADER</small><b>{item.leader}</b><strong>01</strong></div></article>)}</div>
        <p className="fineprint">Ranking labels reproduce the current paper overview snapshot and should be updated together with the final paper results.</p>
      </section>

      <section className="closing"><div><span>PLAY THE WORLD. TEST THE WORLD.</span><h2>From plausible pixels<br/>to persistent worlds.</h2></div><a href="#top">Back to top ↑</a></section>
      <footer><a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a><p>Player-guided evaluation for interactive world models.</p><span>Research preview · 2026</span></footer>
    </main>
  );
}
