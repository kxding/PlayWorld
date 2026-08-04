"use client";

import { useState } from "react";

const demos = [
  { model: "Genie 3", org: "Google DeepMind", caseId: "GC004", family: "Geometry Consistency", duration: "71.2s", src: "/demos/genie3-gc004.mp4", poster: "/posters/genie3-gc004.jpg", prompt: "Move right 10 steps, then return to the original position." },
  { model: "HYWorld2", org: "Tencent", caseId: "OE010", family: "State Evolution", duration: "60.9s", src: "/demos/hyworld2-oe010.mp4", poster: "/posters/hyworld2-oe010.jpg", prompt: "Wait and observe the world as it evolves." },
  { model: "HappyOyster", org: "Alibaba", caseId: "GC016", family: "Geometry Consistency", duration: "60.1s", src: "/demos/happyoyster-gc016.mp4", poster: "/posters/happyoyster-gc016.jpg", prompt: "Walk to the ancient pagoda, then look upward at the tower." },
  { model: "LingBot-World", org: "Ant Group", caseId: "OE005", family: "State Evolution", duration: "60.0s", src: "/demos/lingbot-world-oe005.mp4", poster: "/posters/lingbot-world-oe005.jpg", prompt: "Wait and observe continuous scene evolution." },
  { model: "LingBot-World Infinity", org: "Ant Group", caseId: "GC004", family: "Geometry Consistency", duration: "40.0s", src: "/demos/lingbot-infinity-gc004.mp4", poster: "/posters/lingbot-infinity-gc004.jpg", prompt: "Move right 10 steps, then return to the original position." },
  { model: "SANA-WM", org: "NVIDIA", caseId: "OE070", family: "Out-of-sight Evolution", duration: "33.0s", src: "/demos/sana-wm-oe070.mp4", poster: "/posters/sana-wm-oe070.jpg", prompt: "Turn left 180°, then return to the original view." },
  { model: "GameCraft 2", org: "Tencent", caseId: "OE001", family: "State Evolution", duration: "41.3s", src: "/demos/gamecraft2-oe001.mp4", poster: "/posters/gamecraft2-oe001.jpg", prompt: "Wait and observe the visible world evolve." },
  { model: "Hunyuan WorldPlay", org: "Tencent", caseId: "OE033", family: "State Evolution", duration: "40.8s", src: "/demos/hunyuan-worldplay-oe033.mp4", poster: "/posters/hunyuan-worldplay-oe033.jpg", prompt: "Slowly move the camera to the right." },
  { model: "Matrix-Game 3", org: "Skywork AI", caseId: "OE030", family: "State Evolution", duration: "33.5s", src: "/demos/matrixgame3-oe030.mp4", poster: "/posters/matrixgame3-oe030.jpg", prompt: "Follow the silver SUV down the spiral ramp, then tilt back up." },
];

const findings = [
  { title: "Geometry Consistency", leader: "HYWorld2", score: "3.40", color: "cyan", note: "Identity, texture, color and spatial layout under viewpoint change." },
  { title: "State Evolution", leader: "Genie 3", score: "1.90", color: "violet", note: "Visible and hidden states must accumulate plausible change over time." },
  { title: "Interaction Fidelity", leader: "LingBot-World", score: "2.44", color: "coral", note: "Contact, support, kinematics, causality and solid boundaries." },
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
          <a href="#overview">Overview</a><a href="#method">Method</a><a href="#suite">Suite</a><a href="#demos">Demos</a><a href="#findings">Findings</a>
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
          <div><strong>3</strong><span>diagnostic dimensions</span></div>
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
        <div className="section-head light-head"><h2>Three ways a world can fail.</h2><p>A capability-specific checklist turns each rollout into localized, traceable evidence.</p></div>
        <div className="pillar-grid">
          <article className="pillar cyan"><span className="pillar-number">01</span><div className="pillar-symbol">⌁</div><h3>Geometry<br/>Consistency</h3><p>Does the same world survive motion and revisit?</p><ul><li>Identity & object count</li><li>Material & color stability</li><li>Relative 3D layout</li><li>Closed-loop return views</li></ul><b>48 cases · GC</b></article>
          <article className="pillar coral"><span className="pillar-number">02</span><div className="pillar-symbol">↯</div><h3>Interaction<br/>Fidelity</h3><p>Do actions cause coherent physical responses?</p><ul><li>Contact & support</li><li>Causal response</li><li>Motion kinematics</li><li>Collision boundaries</li></ul><b>50 cases · IF</b></article>
          <article className="pillar violet"><span className="pillar-number">03</span><div className="pillar-symbol">◌</div><h3>State<br/>Evolution</h3><p>Does the world keep changing—even off-screen?</p><ul><li>Meaningful progression</li><li>Hidden-state continuity</li><li>No reset on reveal</li><li>Temporal causality</li></ul><b>73 cases · OE</b></article>
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
        <div className="suite-strip"><span>171 CASES</span><span>123 OBJECTIVES</span><span>56 ACTION PATTERNS</span><span>797 APPLICABLE QUESTIONS</span><span>1ST + 3RD PERSON</span></div>
      </section>

      <section className="section demos" id="demos">
        <div className="section-kicker">04 / CURATED MODEL ROLLOUTS</div>
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
        <div className="section-kicker light">05 / WHAT WE FIND</div>
        <div className="section-head light-head"><h2>No single model owns the world.</h2><p>Available-video means on a 1–5 scale show different leaders for geometry, evolution, and interaction.</p></div>
        <div className="finding-grid">{findings.map((item,index)=><article className={`finding ${item.color}`} key={item.title}><span>0{index+1}</span><h3>{item.title}</h3><p>{item.note}</p><div><small>CURRENT LEADER</small><b>{item.leader}</b><strong>{item.score}<i>/5</i></strong></div></article>)}</div>
        <p className="fineprint">Scores are available-video means from the current evaluation snapshot, not a final complete leaderboard.</p>
      </section>

      <section className="closing"><div><span>PLAY THE WORLD. TEST THE WORLD.</span><h2>From plausible pixels<br/>to persistent worlds.</h2></div><a href="#top">Back to top ↑</a></section>
      <footer><a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a><p>Player-guided evaluation for interactive world models.</p><span>Research preview · 2026</span></footer>
    </main>
  );
}
