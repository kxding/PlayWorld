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

const rankingFamilies = ["Geometry Consistency", "Interaction Fidelity", "Insight Evolution", "Out-of-sight Evolution"] as const;
type RankingFamily = (typeof rankingFamilies)[number];

const rankings: Record<RankingFamily, string[]> = {
  "Geometry Consistency": ["Genie3", "HappyOyster", "HY-World2", "LingBot-World", "LingBot-World2"],
  "Interaction Fidelity": ["Genie3", "LingBot-World", "HappyOyster", "LingBot-World2", "HY-World2"],
  "Insight Evolution": ["LingBot-World2", "Genie3", "HappyOyster", "LingBot-World", "Gamecraft2"],
  "Out-of-sight Evolution": ["Genie3", "HappyOyster", "LingBot-World", "Gamecraft2", "LingBot-World2 & SANA-WM"],
};

export default function Home() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [rankingFamily, setRankingFamily] = useState<RankingFamily>("Geometry Consistency");
  const active = demos[activeIndex];
  const step = (delta: number) => setActiveIndex((activeIndex + delta + demos.length) % demos.length);

  return (
    <main>
      <nav className="nav" aria-label="Main navigation">
        <a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a>
        <div className="nav-links">
          <a href="#overview">Overview</a><a href="#method">Method</a><a href="#paper">Paper Figures</a><a href="#demos">Demos</a><a href="#findings">Leaderboard</a>
        </div>
        <a className="nav-cta" href="#demos">Demos</a>
      </nav>

      <section className="hero" id="top">
        <div className="eyebrow">PLAYER-GUIDED EVALUATION FOR INTERACTIVE WORLD MODELS</div>
        <h1>PlayWorld</h1>
        <p className="hero-subtitle">Evaluating whether generated worlds remain consistent, interactive, and temporally coherent over long rollouts.</p>
        <div className="hero-actions"><a className="button primary" href="#demos">View model demos</a><a className="button ghost" href="#paper">Paper figures</a></div>
        <div className="metric-row">
          <div><strong>171</strong><span>benchmark cases</span></div>
          <div><strong>1,417</strong><span>interactive videos</span></div>
          <div><strong>30–60s</strong><span>long-horizon rollouts</span></div>
          <div><strong>4</strong><span>diagnostic task families</span></div>
        </div>
      </section>

      <section className="section intro" id="overview">
        <div className="section-kicker">01 / THE QUESTION</div>
        <div className="intro-grid"><h2>Long-horizon world model evaluation.</h2><div><p>PlayWorld evaluates complete interactive trajectories instead of isolated frames or endpoints.</p><p>The benchmark tests state persistence, physical response, visible evolution, and hidden-state progression.</p></div></div>
      </section>

      <section className="section method" id="method">
        <div className="section-kicker light">02 / WHAT WE EVALUATE</div>
        <div className="section-head light-head"><h2>Four evaluation families.</h2><p>Each family targets a distinct temporal capability.</p></div>
        <div className="pillar-grid">
          <article className="pillar cyan"><span className="pillar-number">01</span><div className="pillar-symbol">⌁</div><h3>Geometry<br/>Consistency</h3><p>Does the same world survive motion and revisit?</p><ul><li>Identity & object count</li><li>Material & color stability</li><li>Relative 3D layout</li><li>Closed-loop return views</li></ul><b>48 cases · GC</b></article>
          <article className="pillar coral"><span className="pillar-number">02</span><div className="pillar-symbol">↯</div><h3>Interaction<br/>Fidelity</h3><p>Do actions cause coherent physical responses?</p><ul><li>Contact & support</li><li>Causal response</li><li>Motion kinematics</li><li>Collision boundaries</li></ul><b>50 cases · IF</b></article>
          <article className="pillar violet"><span className="pillar-number">03</span><div className="pillar-symbol">◌</div><h3>Insight<br/>Evolution</h3><p>Does a visible process keep making meaningful progress?</p><ul><li>Continuous progression</li><li>Prompt alignment</li><li>Identity preservation</li><li>Physical causality</li></ul><b>30 cases · IE</b></article>
          <article className="pillar gold"><span className="pillar-number">04</span><div className="pillar-symbol">↻</div><h3>Out-of-sight<br/>Evolution</h3><p>Does hidden state continue evolving beyond the current view?</p><ul><li>Hidden-state progression</li><li>Revealed-state difference</li><li>Trajectory continuity</li><li>No reset on reveal</li></ul><b>43 cases · OE</b></article>
        </div>
      </section>

      <section className="section engine">
        <div className="section-kicker">03 / PIPELINE</div>
        <div className="section-head"><h2>Pipeline.</h2></div>
        <div className="pipeline-figures" id="suite">
          <figure><img src="/figures/fig1-overview-latest.jpg" alt="Figure 1 overview of the PlayWorld evaluation pipeline, four task families, and model rankings"/><figcaption>Figure 1. Overview of PlayWorld.</figcaption></figure>
          <figure><img src="/figures/table1-latest.jpg" alt="Table 1 comparison of world-model evaluation benchmarks"/><figcaption>Table 1. Comparison of world-model evaluation benchmarks.</figcaption></figure>
        </div>
      </section>

      <section className="section paper-evidence" id="paper">
        <div className="section-kicker">04 / FROM THE PAPER</div>
        <div className="section-head"><h2>Selected paper figures.</h2><p>Data construction and qualitative results.</p></div>
        <div className="paper-pair">
          <figure><img src="/figures/paper-data-construction.jpg" alt="PlayWorld dataset construction pipeline from initial world settings through objectives, actions, and structured VQA questions"/><figcaption>Data construction pipeline: real starting worlds, long-horizon objectives, executable controls, and structured VQA.</figcaption></figure>
          <figure><img src="/figures/paper-qualitative.jpg" alt="Qualitative PlayWorld failure cases across interaction, geometry, insight, and out-of-sight evolution"/><figcaption>Qualitative evidence: localized failures in interaction, geometry, visible evolution, and hidden-state evolution.</figcaption></figure>
        </div>
      </section>

      <section className="section demos" id="demos">
        <div className="section-kicker">05 / CURATED MODEL ROLLOUTS</div>
        <div className="section-head"><h2>Model demos.</h2><p>One representative rollout over 30 seconds for each model.</p></div>
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
        <div className="section-kicker light">06 / LEADERBOARD</div>
        <div className="section-head light-head"><h2>Model ranking.</h2><p>Select one capability to view its ranking.</p></div>
        <div className="leaderboard-panel">
          <label htmlFor="ranking-family">Ranking metric</label>
          <select id="ranking-family" value={rankingFamily} onChange={(event) => setRankingFamily(event.target.value as RankingFamily)}>
            {rankingFamilies.map((family) => <option key={family} value={family}>{family}</option>)}
          </select>
          <div className="ranking-table-wrap">
            <table className="ranking-table"><thead><tr><th>Rank</th><th>Model</th><th>Capability</th></tr></thead><tbody>
              {rankings[rankingFamily].map((model, index) => <tr key={model}><td>{index + 1}</td><td>{model}</td><td>{rankingFamily}</td></tr>)}
            </tbody></table>
          </div>
        </div>
        <p className="fineprint">Ranking reproduced from the current paper overview figure. Rank 5 in Out-of-sight Evolution is tied.</p>
      </section>

      <footer><a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a><p>Player-guided evaluation for interactive world models.</p><span>Research preview · 2026</span></footer>
    </main>
  );
}
