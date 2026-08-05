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

const heroModels = ["genie", "happyoyster"] as const;
const heroCases = ["gc004", "gc008", "gc016", "gc019", "gc037", "if008", "if030", "if032", "if037", "if043", "oe001", "oe005", "oe010", "oe011", "oe027", "oe030", "oe033", "oe034", "oe036", "oe070"] as const;
const heroVideos = heroCases.flatMap((caseId) => heroModels.map((model) => ({ model, caseId, src: `/hero-mosaic/${model}-${caseId}.mp4` })));

const rankingFamilies = ["Overall", "Geometry Consistency", "Interaction Fidelity", "Insight Evolution", "Out-of-sight Evolution"] as const;
type RankingFamily = (typeof rankingFamilies)[number];

const rankings: Record<RankingFamily, { model: string; score: number }[]> = {
  "Overall": [{model:"Genie3",score:2.12},{model:"HappyOyster",score:1.92},{model:"LingBot-World2",score:1.82},{model:"LingBot-World",score:1.78},{model:"HY-World2",score:1.61},{model:"SANA-WM",score:1.48},{model:"Hunyuan-GameCraft-2",score:1.42},{model:"HY-WorldPlay",score:1.21},{model:"Matrix-Game-3.0",score:1.14}],
  "Geometry Consistency": [{model:"Genie3",score:2.74},{model:"HappyOyster",score:2.54},{model:"HY-World2",score:2.14},{model:"LingBot-World",score:2.11},{model:"LingBot-World2",score:2.04},{model:"SANA-WM",score:1.72},{model:"Hunyuan-GameCraft-2",score:1.62},{model:"Matrix-Game-3.0",score:1.30},{model:"HY-WorldPlay",score:1.12}],
  "Interaction Fidelity": [{model:"Genie3",score:2.40},{model:"LingBot-World",score:2.23},{model:"HappyOyster",score:2.15},{model:"LingBot-World2",score:2.13},{model:"HY-World2",score:2.06},{model:"SANA-WM",score:1.89},{model:"HY-WorldPlay",score:1.63},{model:"Hunyuan-GameCraft-2",score:1.52},{model:"Matrix-Game-3.0",score:1.25}],
  "Insight Evolution": [{model:"LingBot-World2",score:1.95},{model:"Genie3",score:1.51},{model:"HappyOyster",score:1.47},{model:"LingBot-World",score:1.33},{model:"Hunyuan-GameCraft-2",score:1.21},{model:"HY-World2",score:1.13},{model:"SANA-WM",score:1.13},{model:"HY-WorldPlay",score:1.01},{model:"Matrix-Game-3.0",score:1.00}],
  "Out-of-sight Evolution": [{model:"Genie3",score:1.81},{model:"HappyOyster",score:1.54},{model:"LingBot-World",score:1.43},{model:"Hunyuan-GameCraft-2",score:1.31},{model:"LingBot-World2",score:1.16},{model:"SANA-WM",score:1.16},{model:"HY-World2",score:1.09},{model:"HY-WorldPlay",score:1.08},{model:"Matrix-Game-3.0",score:1.00}],
};

const benchmarkRows = [
  ["WorldScore", "Text + Image + Camera", "no", "no", "no", "~2–10 s", "yes", "no", "no"],
  ["WorldSimBench", "Text + Image", "no", "partial", "no", "~2–10 s", "no", "no", "partial"],
  ["WorldMark", "Image + Actions", "yes", "no", "no", "20 / 40 / 60 s", "yes", "no", "no"],
  ["WBench", "Text + Image + Camera / Actions", "yes", "no", "yes", "~5–10 s", "yes", "partial", "yes"],
  ["WorldRoamBench", "Image + Actions", "yes", "no", "yes", "10–60 s", "yes", "partial", "yes"],
  ["MemoBench", "Text + Image + Camera", "no", "no", "yes", "~5–10 s", "yes", "yes", "no"],
  ["Omni-WorldBench", "Text + Image + Camera", "no", "no", "yes", "3–6 s", "partial", "yes", "yes"],
  ["PlayWorld (Ours)", "Text + Image + Objective", "yes", "yes", "yes", "10–60 s", "yes", "yes", "yes"],
] as const;

const vqaRows = [
  ["Web", "Genie3", "2.74", "2.40", "1.51", "1.81", "2.12"],
  ["Web", "LingBot-World", "2.11", "2.23", "1.33", "1.43", "1.78"],
  ["Web", "LingBot-World2", "2.04", "2.13", "1.95", "1.16", "1.82"],
  ["Web", "HY-World2", "2.14", "2.06", "1.13", "1.09", "1.61"],
  ["Web", "HappyOyster", "2.54", "2.15", "1.47", "1.54", "1.92"],
  ["Local", "SANA-WM", "1.72", "1.89", "1.13", "1.16", "1.48"],
  ["Local", "Hunyuan-GameCraft-2", "1.62", "1.52", "1.21", "1.31", "1.42"],
  ["Local", "HY-WorldPlay", "1.12", "1.63", "1.01", "1.08", "1.21"],
  ["Local", "Matrix-Game-3.0", "1.30", "1.25", "1.00", "1.00", "1.14"],
] as const;

const videoQualityRows = [
  ["Web", "Genie3", "0.520", "0.752", "0.990", "0.978", "0.986", "0.845"],
  ["Web", "LingBot-World", "0.511", "0.720", "0.980", "0.963", "0.980", "0.831"],
  ["Web", "LingBot-World2", "0.515", "0.740", "0.978", "0.956", "0.969", "0.832"],
  ["Web", "HY-World2", "0.474", "0.678", "0.991", "0.995", "0.912", "0.810"],
  ["Web", "HappyOyster", "0.497", "0.737", "0.995", "0.990", "0.995", "0.843"],
  ["Local", "SANA-WM", "0.518", "0.726", "0.989", "0.965", "0.982", "0.836"],
  ["Local", "Hunyuan-GameCraft-2", "0.501", "0.678", "0.983", "0.952", "0.980", "0.816"],
  ["Local", "HY-WorldPlay", "0.477", "0.615", "0.989", "0.952", "0.955", "0.798"],
  ["Local", "Matrix-Game-3.0", "0.441", "0.660", "0.989", "0.969", "0.952", "0.802"],
] as const;

const memoryRows = [
  ["Web", "Genie3", "0.887", "0.856", "0.298", "44.28"],
  ["Web", "LingBot-World", "0.922", "0.835", "0.269", "45.45"],
  ["Web", "LingBot-World2", "0.914", "0.823", "0.279", "48.87"],
  ["Web", "HY-World2", "0.907", "0.898", "0.346", "50.24"],
  ["Web", "HappyOyster", "0.918", "0.884", "0.305", "44.40"],
  ["Local", "SANA-WM", "0.844", "0.859", "0.163", "46.19"],
  ["Local", "Hunyuan-GameCraft-2", "0.904", "0.837", "0.150", "64.90"],
  ["Local", "HY-WorldPlay", "0.910", "0.874", "0.180", "47.52"],
  ["Local", "Matrix-Game-3.0", "0.873", "0.657", "0.335", "63.72"],
] as const;

const statusMark = (value: "yes" | "no" | "partial") => value === "yes" ? "✓" : value === "no" ? "✕" : "~";

export default function Home() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [rankingFamily, setRankingFamily] = useState<RankingFamily>("Overall");
  const active = demos[activeIndex];
  const step = (delta: number) => setActiveIndex((activeIndex + delta + demos.length) % demos.length);

  return (
    <main>
      <nav className="nav" aria-label="Main navigation">
        <a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a>
        <div className="nav-links">
          <a href="#top">Overview</a><a href="#method">Method</a><a href="#gallery">Pipeline</a><a href="#demos">Demos</a><a href="#leaderboard">Leaderboard</a>
        </div>
        <a className="nav-cta" href="#demos">Demos</a>
      </nav>

      <section className="hero" id="top">
        <div className="hero-media" aria-hidden="true">
          {heroVideos.map((item) => <div className="hero-video-panel" key={`${item.model}-${item.caseId}`}><video autoPlay muted loop playsInline preload="metadata"><source src={item.src} type="video/mp4"/></video></div>)}
        </div>
        <div className="hero-shade"/>
        <div className="hero-content">
          <div className="eyebrow">PLAYER-GUIDED EVALUATION FOR INTERACTIVE WORLD MODELS</div>
          <h1>PlayWorld</h1>
          <p className="paper-title">Benchmarking World Models with Agent Players over Long-Horizon Objectives</p>
          <p className="paper-authors">Kaixin Ding · Xi Chen · Minghong Cai · Zhiyuan Xu · Yiyang Wang · Yuxiang Lu · Junyi Li · Shuyang Chen · Yuan Gao · Xin Tao · Pengfei Wan · Hengshuang Zhao</p>
          <p className="paper-affiliations">Kuaishou Technology · The University of Hong Kong</p>
          <div className="hero-stats" aria-label="Benchmark summary">
            <div><strong>171</strong><span>Cases</span></div><div><strong>1,417</strong><span>Videos</span></div><div><strong>30–60s</strong><span>Rollouts</span></div><div><strong>9+</strong><span>Models</span></div>
          </div>
          <div className="hero-links" aria-label="Project links"><a href="#gallery">Paper</a><a href="#gallery">GitHub</a><a href="#leaderboard">Leaderboard</a><a href="#gallery">Dataset</a></div>
        </div>
      </section>

      <section className="section method" id="method">
        <div className="section-kicker light">01 / WHAT WE EVALUATE</div>
        <div className="section-head light-head"><h2>Four evaluation families.</h2><p>Each family targets a distinct temporal capability.</p></div>
        <div className="pillar-grid">
          <article className="pillar cyan"><span className="pillar-number">01</span><div className="pillar-symbol">⌁</div><h3>Geometry<br/>Consistency</h3><p>Does the same world survive motion and revisit?</p><ul><li>Identity & object count</li><li>Material & color stability</li><li>Relative 3D layout</li><li>Closed-loop return views</li></ul><b>48 cases · GC</b></article>
          <article className="pillar coral"><span className="pillar-number">02</span><div className="pillar-symbol">↯</div><h3>Interaction<br/>Fidelity</h3><p>Do actions cause coherent physical responses?</p><ul><li>Contact & support</li><li>Causal response</li><li>Motion kinematics</li><li>Collision boundaries</li></ul><b>50 cases · IF</b></article>
          <article className="pillar violet"><span className="pillar-number">03</span><div className="pillar-symbol">◌</div><h3>Insight<br/>Evolution</h3><p>Does a visible process keep making meaningful progress?</p><ul><li>Continuous progression</li><li>Prompt alignment</li><li>Identity preservation</li><li>Physical causality</li></ul><b>30 cases · IE</b></article>
          <article className="pillar gold"><span className="pillar-number">04</span><div className="pillar-symbol">↻</div><h3>Out-of-sight<br/>Evolution</h3><p>Does hidden state continue evolving beyond the current view?</p><ul><li>Hidden-state progression</li><li>Revealed-state difference</li><li>Trajectory continuity</li><li>No reset on reveal</li></ul><b>43 cases · OE</b></article>
        </div>
      </section>

      <section className="section engine" id="gallery">
        <div className="section-kicker">02 / PIPELINE</div>
        <div className="section-head"><h2>Pipeline.</h2></div>
        <div className="pipeline-figures">
          <figure><img src="/figures/fig1-overview-latest.jpg" alt="Overview of the PlayWorld evaluation pipeline, four task families, and model rankings"/><figcaption>Overview of PlayWorld</figcaption></figure>
          <div className="benchmark-table-block">
            <h3>Comparison of world-model evaluation benchmarks</h3>
            <p>✓ full coverage · ✕ no coverage · ~ partial coverage</p>
            <div className="benchmark-table-scroll">
              <table className="benchmark-table">
                <thead><tr><th>Benchmark</th><th>Input</th><th>Unified cross-model</th><th>Closed-loop adaptation</th><th>Revisit trajectory</th><th>Time scale / video</th><th>Geometry consistency</th><th>State evolution</th><th>Interaction fidelity</th></tr></thead>
                <tbody>{benchmarkRows.map((row) => <tr key={row[0]}>{row.map((cell, index) => index < 2 || index === 5 ? <td key={index}>{cell}</td> : <td key={index} className={`status status-${cell}`}>{statusMark(cell as "yes" | "no" | "partial")}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section className="section demos" id="demos">
        <div className="section-kicker">03 / CURATED MODEL ROLLOUTS</div>
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

      <section className="section findings" id="leaderboard">
        <div className="section-kicker light">04 / LEADERBOARD</div>
        <div className="section-head light-head"><h2>Model ranking.</h2><p>Select one capability to view its ranking.</p></div>
        <div className="leaderboard-panel">
          <label htmlFor="ranking-family">Ranking metric</label>
          <select id="ranking-family" value={rankingFamily} onChange={(event) => setRankingFamily(event.target.value as RankingFamily)}>
            {rankingFamilies.map((family) => <option key={family} value={family}>{family}</option>)}
          </select>
          <div className="ranking-table-wrap">
            <table className="ranking-table"><thead><tr><th>Rank</th><th>Model</th><th>Score</th></tr></thead><tbody>
              {rankings[rankingFamily].map((entry) => <tr key={entry.model}><td>{rankings[rankingFamily].findIndex((candidate) => candidate.score === entry.score) + 1}</td><td>{entry.model}</td><td>{entry.score.toFixed(2)}</td></tr>)}
            </tbody></table>
          </div>
        </div>
        <p className="fineprint">Complete nine-model ranking from the current paper results. Equal scores share a rank.</p>
        <div className="result-tables">
          <article className="result-table-card">
            <div className="result-table-head"><h3>VQA-based evaluation</h3><p>Scores range from 1 to 5. Overall is the unweighted mean of the four dimensions.</p></div>
            <div className="result-table-scroll">
              <table className="result-table">
                <thead><tr><th>Setting</th><th>Model</th><th className="group-geometry">Geometry consistency ↑</th><th className="group-interaction">Interaction fidelity ↑</th><th className="group-insight">Insight evolution ↑</th><th className="group-oos">Out-of-sight evolution ↑</th><th>Overall ↑</th></tr></thead>
                <tbody>{vqaRows.map((row) => <tr key={row[1]}>{row.map((cell, index) => <td key={index}>{index === 0 ? <span className={`setting-badge ${cell.toLowerCase()}`}>{cell}</span> : cell}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </article>

          <article className="result-table-card">
            <div className="result-table-head"><h3>Basic video quality</h3><p>Five normalized components and their mean. Higher is better.</p></div>
            <div className="result-table-scroll">
              <table className="result-table compact-results">
                <thead><tr><th>Setting</th><th>Model</th><th>Aes. ↑</th><th>Img. ↑</th><th>Mot. ↑</th><th>Flick. ↑</th><th>Temp. ↑</th><th>Avg. ↑</th></tr></thead>
                <tbody>{videoQualityRows.map((row) => <tr key={row[1]}>{row.map((cell, index) => <td key={index}>{index === 0 ? <span className={`setting-badge ${cell.toLowerCase()}`}>{cell}</span> : cell}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </article>

          <article className="result-table-card">
            <div className="result-table-head"><h3>Memory consistency and action alignment</h3><p>Higher is better for Geo3D and DSCctx; lower is better for translation and rotation error.</p></div>
            <div className="result-table-scroll">
              <table className="result-table compact-results">
                <thead><tr><th>Setting</th><th>Model</th><th className="group-memory">Geo3D ↑</th><th className="group-memory">DSCctx ↑</th><th className="group-action">Translation error ↓</th><th className="group-action">Rotation error (°) ↓</th></tr></thead>
                <tbody>{memoryRows.map((row) => <tr key={row[1]}>{row.map((cell, index) => <td key={index}>{index === 0 ? <span className={`setting-badge ${cell.toLowerCase()}`}>{cell}</span> : cell}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </article>
        </div>
      </section>

      <footer><a className="brand" href="#top"><span className="brand-mark">P</span><span>PlayWorld</span></a><p>Player-guided evaluation for interactive world models.</p><span>Research preview · 2026</span></footer>
    </main>
  );
}
