"""VQA scoring rubric and prompt for WorldModelBenchMark videos.

This module intentionally contains no endpoint, credential, or filesystem logic. It
defines the comparable non-task-specific metric used by the batch evaluators.
"""

from __future__ import annotations

import json
from typing import Any


DEFAULT_FPS = 10
SCORE_MIN = 1
SCORE_MAX = 5


GENERIC_POLICY = {
    "task_specific_scoring": (
        "Do not include task_specific in the final non-task-specific score. "
        "Use it to identify the required-action phase and first completion point. "
        "Only post-completion over-travel may contribute the separately capped adjustment."
    ),
    "normalization_policy": {
        "score_scale": "Report comparable final scores on a 1-5 scale.",
        "exclude_from_denominator": (
            "Exclude task_specific and any question with applicable=false or weight=0. "
            "N/A means ignore the category, not subtract points."
        ),
        "final_score_formula": (
            "base_non_task_score_1_to_5 is the weighted average of applicable non-task-specific "
            "category scores during the required-action phase, using question weight when present "
            "and 1 otherwise. final_score_1_to_5 = clamp(base_non_task_score_1_to_5 + "
            "post_completion_adjustment, 1, 5), where the adjustment is between -1 and 0."
        ),
    },
    "moving_camera_reference_policy": (
        "Before scoring, perform camera-motion disambiguation across adjacent 10-fps "
        "frames using at least two persistent structural anchors. Reference objects may "
        "naturally change screen position/order/scale, leave view, become occluded, or "
        "be passed as the camera pans, rotates, translates, or changes viewpoint. Treat "
        "content entering a newly revealed region as non-comparable, not replacement or "
        "duplication. A hard reset requires both no plausible continuous camera transform "
        "and a simultaneous unsupported identity/topology contradiction in at least two "
        "verified persistent anchors; otherwise hard_reset_claimed must be no."
    ),
    "conditional_visibility_policy": (
        "A case-specific required object must be present and consistent when the sampled "
        "frames actually show or revisit its anchored region. Do not require the camera "
        "to visit that region or complete the requested camera path."
    ),
    "static_tail_policy": (
        "Static-tail treatment is benchmark-group specific. For OE, a physically "
        "reasonable terminal rest receives no penalty. For out-of-sight OE, an artificial "
        "frozen or copy-pasted unfinished ending must lower the applicable "
        "hidden_state_progression, revealed_state_difference, and trajectory_continuity "
        "category scores instead of applying a separate final-score deduction."
    ),
    "sampling_policy": (
        "Use two synchronized full-video evidence streams. Primary temporal evidence is "
        "sampled at 10 fps, rendered as 384x216 cells in chronological 5x5 contact "
        "sheets. Detail evidence is sampled at 0.5 fps, rendered as 800x450 cells in "
        "chronological 2x2 contact sheets. Use primary sheets for adjacent-frame motion "
        "and continuity, and detail sheets for fine identity, texture, color, material, "
        "boundary, and localized artifact inspection."
    ),
}


SCORING_INSTRUCTIONS = (
    "The supplied evidence has two explicitly labeled streams. PRIMARY sheets contain 10-fps, 384x216 cells in chronological 5x5 row-major order. DETAIL sheets contain 0.5-fps, 800x450 cells in chronological 2x2 row-major order. Inspect both streams before scoring.",
    "Use PRIMARY evidence for motion, trajectory, collision timing, short-lived corruption, adjacent-frame correspondence, and temporal continuity. Use DETAIL evidence for fine object identity, texture, material, color, small boundary defects, and high-resolution confirmation. A detail sample is two seconds from the next detail sample and must not be treated as adjacent 0.1-second motion evidence.",
    "Contact-sheet boundaries and black padding are presentation artifacts, not generated-video defects. Within every sheet, read cells left-to-right then top-to-bottom; continue chronologically into the next sheet with the same label.",
    "MANDATORY FIRST PASS: before category scoring, inspect adjacent uniformly sampled frames and distinguish camera pan, rotation, translation, orbit, advance, retreat, perspective, parallax, occlusion, and frame-edge entry/exit from scene change. Track at least two structural anchors such as door frames, wall corners, floor or curb lines, windows, radiators, fixed furniture, or facade boundaries.",
    "Segment the video into continuously tracked local world regions. A region first revealed after camera movement is presumptively new and non-comparable to the initial region. Do not treat a different visible object set as replacement, disappearance, duplication, or reset.",
    "Screen coordinates are projections, not world coordinates. Left/right screen position, apparent scale, and screen ordering may change when the camera moves, passes an object, or views a facade from another side. These projection changes alone cannot lower identity_id or relative_position.",
    "Visual similarity, object category, OCR/sign text, or appearing on the same side of the frame cannot establish same-object or same-region correspondence. Similar content in a newly revealed region is not duplication unless continuous tracking or at least two independent persistent world anchors prove a contradictory second instance.",
    "A hard cut/reset is valid only when both conditions hold across a named adjacent-frame interval: no plausible continuous camera transform explains the transition, and at least two verified persistent structural anchors simultaneously show unsupported replacement, teleportation, or topological contradiction. List the interval and anchors. If either condition is absent or uncertain, set hard_reset_claimed=no and do not use reset, duplication, or anchor-swap language as scoring evidence.",
    "Score only the listed applicable non-task-specific categories.",
    "Do not infer or score omitted task_specific or N/A questions.",
    "Exclude task_specific, applicable=false, and weight=0 categories from the denominator; N/A means ignore, not subtract points.",
    "Use 1-5 per category: 1=failed/very poor, 3=partial/acceptable, 5=yes/excellent.",
    "Compute base_non_task_score_1_to_5 as the weighted average of applicable category scores using the supplied weights.",
    "First compute base_non_task_score_1_to_5 as the weighted category average. Then compute final_score_1_to_5 = clamp(base_non_task_score_1_to_5 + post_completion_adjustment, 1, 5), with post_completion_adjustment constrained to [-1.0, 0.0].",
    "Follow each question and its scoring_notes exactly.",
    "Treat case_specific_evaluation_policy as authoritative for the named case and apply its score levels, caps, valid outcomes, and known disambiguations before computing the final score.",
    "Only listed question subjects and case key_objects may contribute category penalties. Do not introduce an unlisted actor, prop, or task-completion failure as identity, texture, color, or relative-position evidence.",
    "Treat case_visibility_requirements.visibility_guidance and case_visibility_requirements.known_invalid_findings as authoritative case disambiguation. Never use a known-invalid finding as evidence, even with different wording.",
    "Before any identity, texture, color, or relative-position penalty, establish that the compared observations are the same object or the same local world region using at least two independent spatial anchors. Useful anchors include the same side of a fixed doorway, the same wall-floor corner, the same parent/support surface, co-visible neighbors, and continuous frame-to-frame motion. Semantic similarity, object category, sign text, or generic proximity to a doorway is not sufficient by itself.",
    "If two candidate objects are ever co-visible, they are distinct objects and must never be treated as one object transforming into the other. If same-object correspondence remains ambiguous, do not lower identity, texture, or color scores for that comparison.",
    "After correspondence is established, apply a separate visibility gate before any missing-object penalty. The object's expected image projection must lie inside the frame and be unoccluded. If it continuously exits through a frame edge, is cropped by a closer view, or is geometrically occluded, mark it not observable and do not call it disappeared. A support object remaining visible does not imply that an attached object's out-of-frame extent should also be visible.",
    "An absence penalty requires an uncropped view of the same anchored location where the object's expected projection is visibly empty or replaced. Cite both the correspondence anchors and the visibility evidence.",
    "Evaluate background consistency separately from foreground-object matching. Track only background patches established by at least two structural anchors such as door/window frames, wall corners, floor boundaries, facade seams, curb lines, or skyline geometry. Penalize visible warping, drift, replacement, or hard reset of the same anchored background patch; allow parallax and genuinely newly revealed background regions.",
    "Apply case-specific visibility requirements only when the sampled frames actually show or revisit the anchored region. Missing, replaced, duplicated, or structurally changed required objects in that region must be penalized.",
    "Do not penalize an object merely because its region is never visited, it leaves the field of view naturally, or a visible foreground object geometrically occludes it. Do not require completion of the requested path.",
    "For contact/support, penalize only visible physical failures such as floating, sinking, clear sliding against surface texture, or translation without plausible support.",
    "For motion/trajectory, judge visible physical quality and continuity. Do not penalize missing a requested direction, 360-degree orbit, target, or return view.",
    "For identity/appearance/color, judge adjacent-frame consistency and actual reappearances. Natural occlusion, leaving view, or failure to revisit the initial view is not a failure by itself.",
    "For causal/spatial/no-reset, penalize visible warping, drift, hard reset, teleportation, impossible spatial inconsistency, or inconsistent reappearance, not task-direction mismatch by itself.",
    "For collision/boundary, penalize visible clipping, passing through objects, implausible contact, or failure to respond at a contacted boundary. Avoiding contact is not a collision failure.",
    "Split the video at the first clear completion of the requested prompt action. Compute category scores and the base_non_task_score_1_to_5 primarily from the required-action phase through that first completion.",
    "A fully static tail after completion is acceptable. Extra motion after completion is secondary and must not lower category base scores. If the camera clearly continues far beyond the requested stopping point, apply a modest post_completion_adjustment of -0.5 to -1.0 for prompt overrun; use -1.0 for extensive continued travel. Any visible world corruption confined to that extra tail is described under background_consistency but remains inside the same total 1.0-point cap.",
    "If a visible inconsistency begins before the requested action is first completed, score it normally in the applicable category; the post-completion cap does not protect failures in the required-action phase.",
    "requested_action_completion is used to segment phases, not to score task success in the category base. If the action is incomplete or uncertain, do not lower category scores merely for that fact and do not cite task failure in summary_zh; score only listed non-task-specific visible failures.",
    "Use adjacent uniformly sampled frames for temporal and geometric judgments.",
    "Use sampling.primary.fps and sampling.primary.sample_interval_seconds for adjacent temporal judgments; runtime sampling overrides any legacy case note naming a fixed fps. Use sampling.detail only for its stated high-resolution confirmation role. Before claiming teleportation, compare displacement with elapsed sampled time, the subject's visible speed, direction, gait or running pose, scale, perspective, and distance to a frame edge or occluder. A fast-running person or animal may move substantially between samples, and a subject that follows a coherent trajectory out through the frame edge has not teleported. Claim teleportation only when the displacement is physically unreachable over the actual sampled interval and cannot be explained by camera motion, perspective, occlusion, or ordinary frame exit.",
    "Do not cite task-completion failures as evidence. Describe the visible non-task-specific failure instead, such as disappearance, hallucinated objects, hard reset, teleportation, warping, or inconsistent reappearance.",
)


IF_SCORING_INSTRUCTIONS = (
    "For IF cases, hold durations and action_sequence timing are control hints, not hard evaluation cutoffs. Never end the required interaction phase merely because the nominal hold time elapsed.",
    "For every third-person IF case, separately assign if_instruction_following_check without changing any raw 1-5 physical-quality category or final score. Judge whether the named controllable subject visibly progresses along the prompt-directed forward, approach, traversal, or interaction trajectory. PASS means the requested controlled motion is substantially performed. PARTIAL means there is clear prompt-directed subject progress but the trajectory or interaction is incomplete. FAIL means there is no prompt-directed subject progress: the subject remains static or nearly static, only the camera/background moves, a different entity moves, or the subject performs only unrelated, lateral, opposite-direction, or retreat motion. One or a few visible prompt-directed steps before a plausible nearby obstacle, interruption, or incomplete outcome qualify as PARTIAL rather than FAIL; a physically resolved nearby blocking interaction may qualify as PASS. Set instruction_following_score=1 for PASS/PARTIAL and 0 for FAIL. For first-person IF cases set applicable=no and do not apply this gate.",
    "Use the full 1-5 range for every IF category and additionally assign interaction_quality_level_1_to_5 as the authoritative overall physical-interaction quality level. Level 1 means no interaction, a catastrophic interaction failure, or a copy-pasted/frozen subject with no meaningful progress, and caps the final score at 1. Level 2 means a real attempt exists but is extremely weak or severely implausible, and caps the final score at 2. Level 3 means a clear partial interaction occurs with a major defect. Level 4 means the interaction is mostly coherent with only minor defects. Level 5 means a complete and physically coherent interaction with no material defect. The assigned level always caps the final IF score.",
    "Do not collapse every imperfect or incomplete IF result to 1. Verified meaningful subject motion with some interaction progress must normally receive at least interaction quality level 2. A clear partial physical response must receive level 3. Reserve category score 1 for direct severe evidence relevant to that category; use 2 or 3 for weak or partial evidence.",
    "Distinguish an interaction-quality level from its weakest category score. When a subject makes clear, sustained world-space progress along the intended physical route, reaches or continuously uses the relevant surface, remains within valid boundaries, and avoids catastrophic penetration or teleportation, the overall interaction is a clear partial interaction and must receive interaction quality level 3 or higher even if motion_kinematics or contact_support is only 2 because the gait is rigid, sliding, poorly articulated, or lacks visible weight transfer. Keep those defects in their category scores. Use interaction quality level 2 only when the attempted progress itself is extremely brief, weak, largely ineffective, or the overall physical process is severely incoherent rather than merely flawed in one or two categories.",
    "Judge completion relative to what can physically occur within the visible scene and duration. Do not require an unshown terminal event merely to prove that a valid process occurred. For example, several seconds of coherent downward acceleration after leaving a cliff is clear level-3 fall evidence; continued falling is physically valid when no landing surface or expected impact is yet visible, and lack of a landing must not reduce it to 1-2. Apply the same principle to other short but clearly observable contact, submersion, opening, bending, displacement, or impact processes.",
    "Apply an IF subject-motion diagnostic when the case expects the main person to move or initiate a physical interaction. If that person remains fully or nearly fully static throughout the video and makes no meaningful subject-motion progress, score motion_kinematics and any untested target-relevant contact, causal, or collision categories low and assign interaction quality level 1. Camera motion, background motion, animation of unrelated objects, or tiny idle jitter does not count as subject-motion progress.",
    "Before declaring an IF subject fully or nearly fully static, inspect the entire chronology rather than one long pause or a short local window. Compare at least the first stable frame, quarter points, and final stable frame using the subject's world-relative position, apparent scale, distance to path/fence/building anchors, limb pose, gait articulation, and accumulated displacement. Any clearly visible walking interval or substantial coherent change relative to world-fixed anchors disproves a full-video static claim. A long pause before, between, or after walking does not erase real motion; score the meaningful moving and interaction phases normally.",
    "Do not turn the preceding rule into automatic high motion_kinematics credit. A sustained freeze or long pause between unfinished movement intervals is a temporal motion defect even when accumulated displacement proves that the subject is not fully static. Score a mostly coherent trajectory with one brief pause around 4, clear intermittent motion with one or more long freezes around 3, and movement dominated by severe freezing or ineffective stop-start repetition around 2. Reserve 5 for genuinely sustained, natural motion with at most negligible pauses. Keep this category deduction separate from the full-static cap and from a post-completion static-tail adjustment.",
    "Immediate-obstacle exception: before applying inactivity or interaction-quality level 1, inspect whether a solid chair, wall, railing, furniture item, or other boundary already blocks the requested direction within roughly one natural step. If the obstacle occupies the intended path and leaves no plausible forward clearance, a subject that remains outside the solid volume and plausibly stops, settles, braces, or simply cannot advance is already exhibiting a resolved blocking interaction, even when visible displacement or stepping is minimal. Do not require the subject to walk through the obstacle, reach a farther prompt target, or perform repeated futile steps. This outcome must not receive interaction quality level 1 merely for low motion; absent another major defect it is at least level 3, and a stable physically coherent blocked state may receive level 4-5. Also allow coherent detouring, stepping/climbing onto or over the object, jumping, vaulting, or physical redirection. Apply the exception only when adjacent frames establish that the obstacle is genuinely within about one step and blocks the path; a frozen subject with clear traversable space ahead remains inactivity, while floating, sinking, teleportation, or crossing through the solid volume remains failure.",
    "Initial-boundary collision exception: if the subject starts already touching, immediately in front of, or geometrically trapped by the named solid boundary, the interaction opportunity exists from the first frame. When the full sequence shows stable support, stable boundary geometry, and no body-part or attached-object penetration, treat remaining stopped outside the boundary as a valid blocking response. collision_boundary may score 4-5 and interaction quality must not be level 1 solely because no additional forward movement is possible. Score any independently visible gait, support, causality, identity, or appearance defect in its own category.",
    "Do not apply the full-static score-1 gate when the person visibly performs any meaningful approach, movement, contact, or physical interaction before becoming static. A static tail after such progress is acceptable regardless of whether it occupies less than half, more than half, or nearly all of the remaining video. Set post_action_static_penalty to 0 and do not lower category scores, interaction quality, or the final score merely because of that tail. Continue to score any independently visible penetration, sliding, identity drift, reset, or other physical defect in its proper category.",
    "For IF, prompt-compatible motion that continues after the requested action first appears complete is not a quality failure, regardless of how long it continues. Extra walking, running, riding, driving, camera following, or continued approach is task-specific over-execution and must not receive any post_completion_adjustment or category deduction merely for duration or extra distance. Set post_completion_adjustment to 0. If the extra interval contains a visible non-task physical defect such as sliding, penetration, identity drift, deformation, teleportation, or scene corruption, score that defect once in its corresponding category without an additional prompt-overrun deduction.",
    "For every IF result, first compute an effective weighted arithmetic mean of applicable non-task category scores. Exclude task_specific, applicable=false, and weight=0. When interaction_quality_level_1_to_5 is 1 or 2, keep subject_identity visible for diagnosis but exclude its score and weight from both the numerator and denominator. When interaction quality is 3, 4, or 5, include subject_identity normally at its displayed weight. Then compute final_score_1_to_5=min(effective weighted mean, interaction_quality_level_1_to_5). Do not apply static-tail or post-completion adjustments.",
    "For collision_boundary, causal_response, and contact_support, inspect the full video for the actual interaction opportunity and outcome. Any later approach, contact, penetration, crossing, sinking, or physical response involving the named wall, water, railing, furniture, terrain boundary, or obstacle remains primary category evidence regardless of timestamp.",
    "Apply an IF target-contact opportunity gate to contact_support and collision_boundary for physical-interaction tasks. If the expected subject makes no meaningful motion and never reaches the relevant target contact/boundary region, assign contact_support=1 and collision_boundary=1; stable initial standing alone is not evidence for successful target contact or support. If the subject makes some meaningful progress but still never reaches or tests the relevant target region, both categories must remain low and may score at most 2. Once the target opportunity is visibly reached or tested, score the actual support and boundary response on the full 1-5 scale.",
    "The target-contact opportunity gate is satisfied when a nearby obstacle within one or a few natural steps is visibly approached and tested, including a coherent blocked stop, deflection, detour, supported step/climb, jump, or vault. Do not keep the score low merely because this valid nearby interaction prevents travel to a farther prompt destination. Social/destination targets do not require body contact, but their relevant approach region must still be meaningfully reached before claiming the interaction was demonstrated.",
    "The interaction phase ends only after the named subject has either completed a physically resolved interaction with the relevant boundary/surface, become validly blocked and settled, or the full video ends. A nominal action completion timestamp cannot protect a later clipping or pass-through as a static or post-completion tail.",
    "If the subject visibly passes through a solid named boundary, collision_boundary must be 1 with answer=no. Apply the same full-video event evidence to causal_response and contact_support when applicable.",
    "Score collision_boundary by the visible boundary outcome, not by task completion alone. A subject that remains outside solid obstacles with no clipping or pass-through should generally receive a high collision_boundary score. A physically plausible stop, deflection, rebound, or settled contact can receive 5.",
    "Use a reasonable-contact checklist for collision_boundary. Treat all of the following as potentially high-scoring outcomes when visibly coherent and free of solid interpenetration: the subject is blocked and stops; detours or walks around the obstacle; makes contact and is redirected; or steps, climbs, runs, or settles onto a chair, curb, terrain surface, or other supportable object while maintaining plausible support. Do not require one unique reaction or require the subject to reach the task target. Judge support quality separately under contact_support and motion_kinematics.",
    "First classify the named target as either a solid physical boundary/contact surface or a social/destination target. Track a solid target from the approach until the interaction resolves: it must remain present, materially recognizable, and geometrically capable of contact unless a visible force or established mechanism plausibly changes it. Score causal_response and collision_boundary low when the environment preemptively removes the interaction opportunity, including a wall splitting or opening as the subject arrives, a door opening without contact or another visible trigger, a fence or barrier disappearing/retracting, a cliff gaining a new road or bridge, or dense tall vegetation spontaneously clearing into a path so the subject never contacts or displaces it.",
    "Do not penalize a causally supported boundary change: a visibly contacted or pushed door may open, an established automatic door may react to proximity, flexible leaves or grass may bend and part under body contact, and a coherent bridge, gate, or route already visible in the scene may be used. Require adjacent-frame evidence of the trigger preceding or coinciding with the response; mere temporal coincidence or the subject approaching is not enough for a high causal score.",
    "An obstacle that disappears, opens, transforms, or generates a route without a plausible trigger is not successful avoidance and must not receive high collision_boundary merely because no penetration occurs. Normally score collision_boundary and causal_response 1-2 according to severity, and cap if_interaction_quality_level_1_to_5 at 2 when this unsupported change is the mechanism that lets the subject continue.",
    "Do not impose physical-contact completion on a social or destination target such as a vendor, pedestrian, service counter, storefront, or meeting point. A subject may validly approach, keep a plausible stopping distance, pause briefly, avoid nearby people or furniture, and then leave. This may receive high causal_response and collision_boundary scores when no solid object is crossed and the scene remains coherent. Departure after an already resolved contact or interaction is also valid and must not lower category scores by itself. Apply any post-completion retreat deduction only when the later motion clearly contradicts a physical-boundary task or introduces a new visible physical defect, not for a natural departure from a social/destination interaction.",
    "Do not mistake ordinary occlusion, camera tracking, or the body passing behind an object for penetration. Assign a severe collision_boundary penalty only when adjacent frames show the subject occupying or crossing the solid volume, passing through a named wall/glass panel/railing, or visibly failing to respond after actual contact.",
    "Distinguish severe penetration from an avoided or unresolved interaction. If the subject approaches or rushes toward the named boundary but then reverses or retreats without visible penetration and without a plausible blocking/contact response, apply only a one-point deduction from the otherwise appropriate collision_boundary score (normally 4 rather than 1). Do not treat this as pass-through and do not assign 1 solely because contact was not demonstrated.",
    "If a meaningfully moving subject never approaches the relevant boundary, do not invent penetration or a collision failure; judge only visible boundary evidence. However, when the case expects subject motion and the subject makes no meaningful spatial progress at all, collision_boundary is 1 because no boundary interaction or response is demonstrated under the IF inactivity gate. State that this is missing interaction evidence, not observed penetration.",
    "For causal_response, absence of a reached interaction opportunity is not by itself a catastrophic score-1 response. Use score 2 when the subject makes meaningful progress toward the interaction but the expected causal event remains largely undemonstrated; use score 3 when a partial response is visible; use 4-5 when the response is mostly or fully plausible.",
    "For contact_support and motion_kinematics, distinguish minor jitter or brief sliding from sustained floating, sinking, foot-contact loss, or implausible translation. Minor defects belong at 4, clear but limited defects at 3, severe sustained defects at 2, and catastrophic persistent failure at 1.",
    "When feet, hooves, wheels, or another support interface are cropped or occluded, do not automatically mark contact_support as failed. Use visible proxy evidence across adjacent frames: rhythmic torso or head bob, vertical oscillation, weight transfer, knee or hip motion, gait-synchronized speed variation, rider bounce, stable mounted height, and coherent scene translation. Positive proxy evidence can support a plausible contact or motion score; absence of both the interface and all expected body-motion proxies is negative evidence when the prompt requires walking, riding, or another supported locomotion. Evidence must come from the sampled frames, never from the prompt or caption alone. Before claiming that a named mount, antler, body part, vehicle component, or tool is visible, identify concrete frames where its recognizable geometry appears; do not mistake game UI, a joystick, reticle, control icon, lamp post, tree branch, or unrelated foreground shape for that entity. Smooth camera translation, turning, or generic scene parallax alone is not rhythmic rider bounce: require repeated vertical oscillation over multiple cycles or another mount-specific motion cue.",
    "For fast IF subjects such as a running dog, judge trajectory continuity in world space across the 10-fps samples. Coherent forward displacement with compatible running articulation and a plausible exit through the image boundary is valid motion, even if the subject covers many pixels between samples. Do not lower motion_kinematics, causal_response, or collision_boundary merely because sparse samples do not overlap pixel-by-pixel.",
    "When a running animal approaches the camera, perspective may rapidly enlarge it and change the visible pose from frontal to side and then rear as it passes the camera. If adjacent samples preserve a coherent approach direction, body articulation, ground contact, and pass-by path, this is one continuous trajectory, not teleportation, reversal, or a hard reset. Also inspect the full early interval before applying an inactivity gate: any clear walking or running by the named subject disproves a claim that it remained static for the entire video, even if it later stops.",
    "Score mixed-quality trajectories across the full relevant interaction. A clearly visible valid phase followed by a severe but non-catastrophic failure should normally land at 2 rather than 1, because real progress occurred. For example, normal stair descent followed by implausible walking or gliding on the water surface is level 2 overall: preserve credit for the valid stairs phase while penalizing the later support and water-response failure. Score 1 only when the later event is a catastrophic category failure such as direct solid penetration or when meaningful progress was never established.",
    "For subject_identity in every IF case, track the named persistent main subject throughout every visible interval. This may be a person, animal, vehicle, robot, boat, tool, gripper, manipulated object, or the persistent visible body/components in a first-person view. It must remain recognizably the same entity, with stable defining clothing, body proportions, face or hair, components, markings, and persistent equipment. The subject and its persistent components must preserve their defining colors, material class, texture, and surface appearance over the long trajectory. Allow changes explained by pose, articulation, apparent scale, perspective, lighting, shadow, motion blur, wetness, physically required deformation, and temporary occlusion. Penalize unsupported gradual or abrupt color drift, material melting, texture drift, surface repainting, noise speckles, blotches, crawling artifacts, or persistent hue changes, as well as morphing, replacement, identity swap, unsupported duplication, fusion, splitting, or a contradictory reappearance. Do not use task completion or ordinary pose change as identity evidence.",
    "Make IF subject_identity eligibility depend only on interaction_quality_level_1_to_5. At levels 1-2, retain the subject_identity category score and evidence for diagnosis but exclude its score and weight from the effective weighted mean so stable appearance cannot rescue absent or weak interaction. At levels 3-5, include subject_identity normally at its supplied weight, so morphing, color drift, material change, texture drift, or noise lowers the result after meaningful interaction has been demonstrated.",
    "For collision_boundary, evaluate the complete collision geometry of the main subject and its visible extensions. Include every body part plus worn, carried, held, ridden, driven, or manipulated items such as loose clothing, backpacks, weapons, paddles, oars, paddleboards, boats, vehicles, and tools. If any such part passes through intact ice, a wall, railing, furniture, terrain, or another solid boundary without plausible breakage or deformation, score collision_boundary as a severe failure. Do not declare collision success merely because the torso avoids penetration while an attached or held object clips through the boundary.",
    "For water-entry cases, inspect the subject relative to the visible shoreline, pool rim, water mask, and waterline across adjacent 10-fps samples. Any sampled frame showing the feet or body crossing into the water region, becoming partly submerged, or remaining visibly inside the pond establishes that the subject reached or entered the water. Do not claim 'never entered water' merely because the crossing is brief between samples or because ripples and splashes are weak. Score entry/contact evidence separately from water causal response: missing ripples, splashes, displacement, or submersion lowers causal_response or support quality but cannot erase observed entry.",
    "After meaningful movement or a resolved physical interaction, a sustained interval in which the main person remains static through the end is an acceptable terminal state. You may report its first sampled frame and duration fraction for diagnostics, but post_action_static_penalty must be 0. Any separate major physical failure after nominal control timing remains in the applicable category base score.",
)


INITIAL_REFERENCE_ONLY_INSTRUCTIONS = (
    "For this case, score only objects and structures present in the first video frame or supplied reference image.",
    "Track an initial object while continuously visible and when its original anchored location clearly reappears, but ignore every object or region first revealed after the first frame.",
    "A later object with the same text, category, or appearance as an initial object is outside this case's scope and must not be called duplication, replacement, texture/color change, or spatial inconsistency unless it visibly occupies or replaces the initial object's original anchored location.",
)


CONTINUOUS_FOREGROUND_FULL_BACKGROUND_INSTRUCTIONS = (
    "For this case, score listed foreground objects only during continuous visibility. Once an initial foreground object exits the frame, do not infer later reappearance, replacement, or absence and do not compare it with later furniture or props.",
    "Continue evaluating anchored background structure throughout the full video. Use at least two structural anchors to judge the same door-frame, wall, floor, room, or facade patch, and penalize genuine background warping, drift, replacement, or reset.",
    "A later view may show stable background while the original foreground object's local wall patch remains outside the frame; award background consistency normally and do not convert foreground non-observability into an identity or relative-position failure.",
)


ROTATION_FINAL_STATE_INSTRUCTIONS = (
    "For a camera-rotation case, always inspect the final stable window and report which listed key objects are visible there. The final state is mandatory evidence, not an optional tail.",
    "When an initial key object reappears in the final view, compare it with the initial observation using its local support surface and at least one additional anchor. A consistent final reappearance is positive identity and relative-position evidence.",
    "Do not call an initial object permanently disappeared or replaced when it is visibly present again in the final window. Objects and tabletop or background regions seen only at intermediate rotation angles may be different world locations and must not be matched by category similarity alone.",
    "If the prompt requests returning to the original angle, use the final view to assess reappearance consistency, but keep any pure angular shortfall or overshoot in the capped prompt-action adjustment rather than using it to erase valid object-consistency evidence.",
)


OE_SCORING_INSTRUCTIONS = (
    "For every OE case, meaningful temporal evolution is mandatory. A video that is entirely or nearly entirely static, frozen, or limited to ineffective oscillation with no observable state or trajectory progress must receive the minimum final_score_1_to_5 of 1.0, even if identity remains perfectly stable.",
    "For out-of-sight OE cases, separately assign oe_instruction_following_check using only the observed camera or controlled-agent action trajectory. PASS means the requested action trajectory is substantially executed. PARTIAL means a meaningful requested trajectory segment is executed but the sequence is incomplete; for a revisit task, passing through the starting camera pose at any intermediate time is sufficient for PARTIAL even when the visible world content differs. FAIL means no meaningful requested trajectory progress occurs or the motion is unrelated/opposite to the requested action. Never use object identity, same-looking visual evidence, background consistency, evolution quality, or whether the returned view contains matching objects to decide this completion verdict. Set instruction_following_score=1 for PASS/PARTIAL and 0 for FAIL. For in-sight OE set applicable=no. This gate does not alter raw OE category scores or the raw 1-5 final score.",
    "Judge dynamicity relative to the named process and its natural spatial scale, not by whole-frame motion magnitude. Small local changes such as pen-tip motion with accumulating ink, chewing with food reduction, liquid-level change, subtle articulation, or short object displacement are meaningful evolution when they match the case.",
    "Before applying the 1.0 gate, inspect the named process over the full chronological sequence and explicitly report its accumulated task-relevant change. Do not mechanically divide in-sight evolution into early/middle/final stages; follow the process described by the prompt. A fixed camera, static background, or small moving region does not make the video static when the named process progresses.",
    "Apply the gate only when the named process has no observable accumulated progress. Repetitive motion is gated only when it returns to the same state without producing the expected writing, consumption, displacement, deformation, state transition, or other case-specific result.",
    "Assign an evolution_quality_level_1_to_5 and use it as an upper bound on the final score: 1 means zero accumulated progress, frozen content, or purely ineffective repetition; 2 means a brief or extremely small real state change followed by severe stagnation; 3 means clear but limited, incomplete, incoherent, or low-quality evolution; 4 means sustained and mostly coherent evolution with a noticeable flaw; 5 means sustained, complete, causally plausible, high-quality evolution.",
    "Do not collapse every imperfect video to 1. Any verified persistent state or trajectory change must receive at least evolution level 2. Clear partial progress must receive level 3. Identity and scene stability may improve category averages but cannot raise the final score above the evolution quality level.",
    "For in-sight evolution, score the continuously visible process over the full chronological sequence without imposing artificial stage boundaries. Require visible progress of the named process, action, state, or trajectory while it remains observable. Camera motion, flicker, breathing-like jitter, or repeated motion that produces no accumulated change is not meaningful evolution.",
    "Apply an intrinsic ongoing-motion check using the prompt and first-frame evidence, not object class alone. When the initial state visibly shows a process that cannot physically pause in mid-course, such as a rocket actively launching with flame and exhaust, an airborne projectile, a falling object, a vehicle already driving, or visibly flowing liquid, require continued plausible trajectory or state evolution while observable. If that active subject remains frozen or copy-pasted while only the camera or background changes, score evolution, prompt_evolution_alignment, and physical_causality low; if there is no genuine accumulated progress anywhere, set evolution quality and final score to 1. Do not apply this rule to a parked vehicle, a rocket waiting on a launch pad, still water, or any subject for which ongoing motion is not established by the prompt or visible initial evidence.",
    "For out-of-sight evolution, use phase comparison only when the prompt/video contains a leave-view then reappearance loop: compare the last anchored visible state before occlusion, the hidden interval only through its causal implications, and the first stable reappeared state. If no such loop occurs, do not force stage labels. Require evidence that the hidden state plausibly progressed while unobserved and that the revealed state differs consistently with that progression. A frozen revealed state, first-frame reset, or unchanged object with no hidden-state progress is low quality.",
    "For out-of-sight evolution, never infer target-subject motion from screen-coordinate displacement, apparent height, scale, framing, parallax, or camera pan/rotation/translation alone. Register the pre-exit and post-return views using stable scene landmarks. To claim camera-independent subject movement, require two independent forms of positive boundary evidence: (A) a concrete change in articulated pose, limb geometry, contact/support, or a persistent local process state; and (B) a concrete change relative to the same uniquely matched stair step, floor edge, railing joint, furniture feature, or other local world anchor. Name the exact before/after evidence for both A and B. Anchor-relative displacement without A is insufficient, and pose jitter without B is insufficient. If the subject has the same pose and the same nearby local details before exit and after return while only the camera viewpoint changes, classify it as frozen/no evolution. Unchanged coupled details such as smoke below an arm, exhaust, splashes, shadows, carried objects, clothing folds, or contact geometry are strong copy-paste evidence when they remain spatially identical with the subject and override an apparent screen-position change. Do not claim that a girl continued climbing merely because she appears higher in the returned frame; prove that she advanced relative to the same uniquely identified stair step and that her articulated pose or local process state changed. The hidden interval itself is unobserved and cannot be cited as evidence that motion continued; infer progression only from verified boundary-state differences.",
    "Adapt the two-evidence motion gate to rigid vehicles without inventing human-like articulation. For a train, tram, bus, or other rigid vehicle, evidence A must be vehicle-local temporal progression such as wheels or bogies changing relative to the rail, successive identifiable carriages or windows crossing the same fixed marker, changing physically consistent occlusion at a signal post or platform edge, coupled exhaust changing with motion, or another continuously tracked vehicle feature. Evidence B must be forward displacement along the same verified rails or roadway relative to one or more fixed world anchors such as sleepers, switches, signal posts, utility poles, platform edges, track joints, or building corners. Camera pan, zoom, train-size change, generic background parallax, or the whole train sliding with an unchanged local configuration does not satisfy either requirement. If no concrete forward progress is verified but the vehicle consistently reappears without identity failure, out-of-sight evolution and the final score are capped at 2; an exact frozen copy with no local temporal change remains evolution level 1.",
    "For every moving vehicle, explicitly identify its front and rear before judging progress. Use persistent geometry appropriate to the vehicle: locomotive cab or nose versus trailing consist, windshield and headlights versus rear window and taillights, aircraft nose and cockpit versus tail, motorcycle front wheel and fork versus rear wheel, or another unmistakable front-rear feature. Then compare the vehicle's anchored world-space displacement with its heading and the local tangent of the same verified rail, lane, runway, or track. A vehicle whose front orientation remains forward but whose world displacement is backward is reversing, not advancing. Do not mistake a camera pass, orbit, viewpoint flip, changed screen direction, or reversed screen ordering for a vehicle turn. Unprompted sustained reversing, backward sliding, or a front-rear swap without a visible turn, steering maneuver, braking-and-reversal event, or prompt instruction is a major trajectory-continuity and physical-causality failure and caps evolution/final quality at 2; if the requested or physically established forward process is wholly replaced by reverse motion, use evolution level 1.",
    "Check motion direction against the prompt, first-frame heading, support geometry, and visible gait or transport mechanism. A returned position is not positive progress when it contradicts the established direction. For a person facing and travelling down stairs or a downward escalator toward a lower landing, an unexplained higher returned position is reverse or physically inconsistent evolution unless a visible turn, reversal, upward walking action, or escalator-direction change occurs. Apply the same directional-causality check to vehicles, queues, falling objects, flowing liquids, and other directional processes.",
    "For every out-of-sight accumulation process, make the primary quantitative comparison between the last stable visible state immediately before the target leaves view and the first stable comparable state after it returns. The first frame may provide context but must not replace this boundary-to-boundary comparison. Coffee or other liquid volume, written or painted marks, assembled parts, consumed amount, deformation, displacement, and other monotonic accumulated results must not decrease, disappear, or revert after return unless a visible physically plausible reversal explains it. An unexplained lower returned coffee level or lost accumulated result is a severe failure in revealed_state_difference, process_accumulation, physical_causality where applicable, and the merged subject_identity/reset dimension.",
    "For OE, distinguish a reasonable terminal rest from an artificial frozen ending without using tail duration or duration fraction. If the action or physical process reaches a plausible stable terminal state and subsequent stillness is expected, set terminal_static_reasonable=yes and do not lower any score. If an out-of-sight process instead abruptly freezes or copy-pastes an unfinished, intrinsically active, or physically unresolved state, do not apply a separate final-score subtraction. Lower each applicable evidence dimension directly: hidden_state_progression for absent or inadequate hidden progress, revealed_state_difference for an unchanged or insufficiently evolved returned state, and trajectory_continuity for an arrested, discontinuous, or physically unresolved trajectory. Use score 1 when the required evidence is absent or the state is an exact frozen copy, and score 2 when some genuine progress exists but is weak or terminates unnaturally. Do not deduct the same freeze again through a static-tail adjustment. Entirely or nearly entirely static video is still handled by the separate no-evolution level-1 gate.",
    "Use body pose, support, and process phase to decide terminal reasonableness. A person frozen mid-step, with one foot raised, limbs caught mid-swing, the torso leaning without settled support, an unfinished reach or contact, a mid-jump or mid-fall pose, or another visibly tense transitional configuration is still in an active process and is not a reasonable terminal rest. The same applies to a vehicle frozen between physically active states, liquid or smoke frozen mid-flow, an unfinished tool stroke, or an unresolved collision/contact. A reasonable terminal rest requires stable support, a naturally settled pose or completed state, and no visual evidence that motion should continue. Record this diagnosis in the terminal-static fields, but keep static_tail_score_adjustment at 0 because the applicable category scores carry the effect.",
    "For out-of-sight evolution, remove namespace prefixes from category names: use hidden_state_progression, revealed_state_difference, trajectory_continuity, no_reset, and process_accumulation rather than out_of_sight_evolution.<name>.",
    "For OE subject_identity, track the same persistent person, animal, vehicle, robot, tool, liquid, queue, evolving object, and relevant equipment across every visible interval and after occlusion or return. Require stable defining clothing, body proportions, components, markings, colors, material class, texture, and surface appearance over the long trajectory. Allow pose, articulation, perspective, lighting, shadow, motion blur, wetness, physically required deformation, prompt-required evolution, and temporary occlusion. Penalize unsupported gradual or abrupt color drift, material melting, texture drift, surface repainting, noise speckles, blotches, crawling artifacts, replacement, category change, duplication, fusion, splitting, or contradictory reappearance. A dynamic subject is not required to preserve an identical pose, pixel appearance, position, or internal state.",
    "Merge OE reset continuity into subject_identity; do not score no_reset as a separate category. The merged subject_identity score must jointly evaluate recognizable entity continuity, defining color/material/texture stability, and whether the subject or its accumulated state resets, reverts, or returns contradictorily after occlusion. Penalize even a mild unsupported whole-object or whole-scene hue shift when it persists across comparable checkpoints, and penalize temporally persistent colored noise points, speckles, crawling dots, blotches, coarse grain, granular corruption, or a newly noisy/dirty texture on the same tracked surface. Do not penalize isolated one-frame compression blocks, resampling artifacts, ordinary sensor-like grain already present in the source, or appearance changes explained by lighting, exposure, motion blur, perspective, wetness, or prompt-required physical evolution.",
    "For OE productive actions such as writing, drawing, coloring, painting, cutting, assembling, or other work that should leave an accumulated result, tool or hand motion alone is not meaningful evolution. Track the same target surface or workpiece and require a visible, localized, persistent state change caused by the observed action.",
    "Score productive-action coherence jointly in insight_evolution, physical_causality, and prompt_evolution_alignment when those categories apply. The produced result must look intentional and temporally connected to the action: handwriting should form recognizable line- or character-like progress rather than random scribbles; a drawing or painting should gain coherent strokes, shapes, shading, or coverage; and successive operations should continue the same task rather than jump to unrelated gestures. Do not require exact text or one artistic interpretation unless the case prompt names a word, symbol, subject, color, region, or outcome; when it does, the visible result must remain recognizably aligned with that requirement.",
    "Require local physical causality for productive actions: the pen, marker, brush, knife, or tool must plausibly contact the target, and the new mark or state change must appear at and after that contact in a path consistent with the tool motion. Penalize jitter with no result, marks appearing away from contact, results appearing before the action, disconnected jumps, random unrelated actions, or changes unsupported by the tool.",
    "Once a productive result is visibly established, it must persist unless a visible, physically plausible erasing, covering, removal, or reversal action explains the change. Newly written text, drawn strokes, paint, cut pieces, assembled parts, or other accumulated work that later disappears, resets, shrinks, or reverts without such a cause is a severe failure in evolution, physical_causality, prompt_evolution_alignment, process_accumulation, and no_reset where applicable.",
    "Use this productive-action scale: 1 means motion with no persistent result, catastrophic reset, or wholly unrelated action; 2 means a real persistent change exists but is largely incoherent, unrecognizable, random, severely discontinuous, or mismatched to a named requirement; 3 means clear meaningful and causally connected but substantially flawed progress; 4 means mostly coherent, recognizable, persistent, prompt-aligned progress with a minor defect; 5 means clear, sustained, physically caused, recognizable, prompt-aligned accumulated work with no material disappearance or reset.",
    "Apply OE subject_identity only after the evolution gate. Evolution quality 1 means identity is diagnostic only and the final score is capped at 1; evolution quality 2 means stable identity cannot rescue the weak process and the final score is capped at 2. Once meaningful evolution reaches quality 3-5, include subject_identity normally at weight 1, so identity, color, material, or texture drift lowers the weighted result after real evolution has been demonstrated.",
    "An OE subject that reappears as an exact static copy of its earlier state despite an expected evolving process is not strong identity evidence. If the video is completely or nearly unchanged, frozen, or copy-pasted with no accumulated state or trajectory progress, give low evolution scores, keep subject_identity at 2 or below for the unchanged dynamic subject, and cap the final score at 1.0.",
    "For OE weighting, every applicable category has equal weight 1. Exclude applicable=false and weight=0 categories. Stable identity cannot bypass the separate dynamicity gate, raise the final score above evolution_quality_level_1_to_5, or compensate for missing evolution.",
)


GC_SCORING_INSTRUCTIONS = (
    "Apply the mandatory camera-motion disambiguation before GC identity or relative-position scoring. Camera-driven changes in visible region, screen position, left/right ordering, scale, and perspective are not world-space mutations.",
    "For every alleged GC hard reset, provide the exact adjacent-frame interval, at least two persistent structural anchors, and evidence that both required reset conditions hold. If the transition is explainable by coherent camera movement or the observations belong to different local regions, hard_reset_claimed must be no and the comparison must be marked non-comparable.",
    "Do not infer duplicated landmarks or swapped anchors from visual/OCR similarity or changed screen ordering. Duplication or world-space swapping requires continuous tracking or two independent persistent anchors that prove the same world region and a simultaneous contradiction.",
    "For every GC case, meaningful camera or agent action progress is mandatory. If the video is entirely or nearly entirely frozen, has no effective camera displacement/orientation change, or only repeats ineffective motion with no accumulated progress, final_score_1_to_5 must be exactly 1.0 regardless of identity or background stability.",
    "Judge action progress relative to the requested action and its natural scale, not by whole-frame optical-flow magnitude. A small but coherent translation, turn, orbit segment, or agent movement is meaningful when it advances the requested action.",
    "Distinguish a genuinely frozen/no-progress video from a static scene observed by a moving camera. Coherent camera translation or rotation is meaningful progress even when furniture and architecture themselves are static.",
    "A static tail after meaningful requested action has visibly occurred or reached its first completion is acceptable and does not trigger the gate. Apply the gate only when the video as a whole lacks meaningful action progress.",
    "Minor action under-travel, over-travel, or angular error after meaningful progress uses the separately capped prompt-action adjustment; it is not the frozen/no-progress gate.",
    "For GC, follow the action structure in the prompt instead of mechanically splitting every video into early, middle, and late thirds. When the prompt contains a loop or return to a previously observed view, compare the anchored state before departure, observations during the excursion only where correspondence is established, and the stable returned/revisited state. Without a loop or revisit, track listed objects continuously at the checkpoints relevant to the prompt.",
    "Actively try to falsify consistency before awarding identity_id or relative_position above 3. Inspect for duplicated, missing, fused, split, stretched, bent, detached, or replaced objects and components, and distinguish real objects from reflections using contact, support, occlusion, and continuous motion.",
    "When a listed object leaves view, verify that the frame boundary or visible occluder geometrically explains its absence. If its anchored support region remains visible and empty, or it fails to reappear when that region is revisited, score the disappearance or replacement as a failure.",
    "For GC color, first establish same-object or same-surface correspondence and visibility, then compare the tracked visible surface across adjacent sampled frames and prompt-relevant reappearances. Penalize unsupported gradual or abrupt intrinsic hue drift, repainting, color flicker or swapping, and temporally generated colored speckles, blotches, crawling dots, or patch noise on that same surface. Allow changes explained by lighting, shadow, exposure, viewing angle, perspective, occlusion, motion blur, wetness, or ordinary compression.",
    "For GC identity_texture, track the same visible material class, surface finish, markings, grain, pattern, lettering, and stable local detail across adjacent sampled frames and prompt-relevant reappearances. Penalize unsupported texture crawling or drift, material melting, pattern replacement or loss, and persistent generated noise such as speckles, blotches, granular corruption, checker patches, or flickering surface artifacts. Do not treat a single ambiguous pixel, isolated compression block, blur, foreshortening, or newly revealed surface as a texture failure; require temporally corroborated evidence on the same tracked surface.",
    "A GC color, texture, or noise claim may lower a category only when the evidence names the localized same surface and cites at least three ordered sampled checkpoints showing a before, developing, and after state under comparable visibility, or two independently anchored reappearance checkpoints with an unambiguous contradiction. A broad interval such as 'throughout the video', comparison of different statues or surfaces, or an unsupported adjective such as changed, melted, noisy, or brown is insufficient. Mark an uncorroborated suspicion as possible and do not lower the category for it.",
    "For noise specifically, require the artifact to persist or recur on the same tracked surface over at least three adjacent samples; isolated JPEG blocks, resampling patterns, one-frame colored pixels, and contact-sheet seams are not generated-video noise. Scores 1-2 require major or widespread verified corruption, 3 indicates a clear moderate defect, 4 a minor localized verified defect, and 5 no verified defect.",
    "Avoid double counting GC appearance failures. A hue-only defect belongs primarily to color; a material, texture, marking, or achromatic surface-noise defect belongs primarily to identity_texture. Lower identity_id as well only when the corruption visibly changes the object's recognizable entity, structure, count, or category.",
    "A score of 5 requires itemized evidence covering the relevant listed objects at multiple checkpoints. Do not resolve ambiguous correspondence in favor of a perfect score, and do not infer consistency for an object that was not actually checked.",
)


OUTPUT_SCHEMA = {
    "base_non_task_score_1_to_5": "weighted category average before any post-completion adjustment",
    "final_score_1_to_5": "number from 1 to 5",
    "category_scores_1_to_5": {
        "category_name": {
            "score": "number from 1 to 5",
            "weight": "number",
            "answer": "yes/partial/no",
            "evidence_zh": "concise visible evidence",
        }
    },
    "excluded_categories": {
        "task_specific": "not scored",
        "other_excluded_if_any": "reason",
    },
    "static_tail_policy_applied": "concise explanation",
    "action_inconsistency_penalties": [],
    "requested_action_completion": {
        "completed": "yes/no/uncertain",
        "first_completion_frame": "sampled frame number or null",
        "evidence_zh": "concise evidence",
    },
    "background_consistency": {
        "required_action_phase_zh": "anchored background evidence before first completion",
        "post_completion_phase_zh": "anchored background evidence after first completion",
    },
    "object_correspondence_checks": [
        {
            "comparison": "objects or regions compared",
            "anchors": ["at least two independent anchors"],
            "same_object_or_region": "yes/no/uncertain",
        }
    ],
    "camera_motion_disambiguation": {
        "intervals_checked": ["adjacent sampled-frame intervals inspected"],
        "continuous_camera_motion": "yes/no/uncertain",
        "tracked_structural_anchors": ["at least two anchors"],
        "newly_revealed_regions_zh": "which observations belong to new/non-comparable regions",
        "evidence_zh": "why the view change is or is not explained by camera motion",
    },
    "hard_reset_check": {
        "hard_reset_claimed": "yes/no",
        "adjacent_frame_interval": "specific interval or none",
        "no_plausible_camera_transform": "yes/no/uncertain",
        "persistent_anchor_contradiction": "yes/no/uncertain",
        "contradicting_anchors": ["at least two only when claimed=yes"],
        "evidence_zh": "both-condition proof or why reset is rejected",
    },
    "post_completion_adjustment": {
        "value": "number from -1.0 to 0.0",
        "evidence_zh": "only extra motion or failures after first prompt completion",
    },
    "final_state_check": {
        "window": "final sampled frame interval inspected",
        "visible_key_objects": ["listed objects visibly present in the final window"],
        "reappearance_consistency_zh": "initial-to-final consistency evidence for rotation cases",
    },
    "oe_dynamicity_check": {
        "mode": "in_sight/out_of_sight/not_applicable",
        "meaningful_evolution": "yes/partial/no",
        "static_or_near_static": "yes/no",
        "ineffective_repetition": "yes/no",
        "evolution_quality_level_1_to_5": "integer 1, 2, 3, 4, or 5 using the OE progression rubric",
        "named_process": "the case-specific process or state expected to evolve",
        "phase_comparison_applicable": "yes only for an out-of-sight leave-and-reappear loop; otherwise no",
        "pre_occlusion_state_zh": "last anchored visible state before leaving view, or not_applicable",
        "hidden_interval_zh": "hidden interval and plausible causal implications, or not_applicable",
        "reappeared_state_zh": "first stable state after reappearance, or not_applicable",
        "post_completion_static_tail": "yes/no",
        "static_tail_first_frame": "sampled frame number or null",
        "terminal_static_reasonable": "yes/no/not_applicable",
        "terminal_pose_or_process_state": "natural_settled_rest/mid_step_or_limb_swing/unstable_lean/unfinished_contact/mid_air_or_fall/active_vehicle_state/flow_frozen/unfinished_tool_action/other_unresolved/not_applicable",
        "support_and_pose_evidence_zh": "feet/support/contact and body or process evidence showing settled completion versus a frozen intermediate state",
        "terminal_state_reasoning_zh": "why the still ending is a plausible completed rest or an artificial unresolved freeze",
        "static_tail_score_adjustment": "always 0; terminal-freeze evidence is represented in applicable OE category scores",
        "static_tail_penalty_zh": "diagnostic explanation only; no separate final-score deduction",
        "camera_independent_subject_motion": "yes/partial/no/not_applicable",
        "stable_world_anchors_compared": ["same stairs, floor edge, railing, furniture, or other local anchors"],
        "articulation_or_local_state_change_zh": "required evidence A: named before/after limb, pose, contact, support, or local-process change",
        "uniquely_matched_anchor_relative_change_zh": "required evidence B: named before/after change relative to the same uniquely identified world feature",
        "two_independent_motion_evidence_requirements_met": "yes/no/not_applicable",
        "expected_world_motion_direction_zh": "direction inferred from prompt, first-frame heading, support geometry, gait, or transport mechanism",
        "returned_motion_direction_consistent": "yes/partial/no/not_applicable",
        "rigid_vehicle_local_progression_zh": "wheel/bogie, carriage/window crossing, fixed-marker occlusion, exhaust, or other vehicle-local evidence",
        "vehicle_front_rear_identification_zh": "persistent geometry used to identify the vehicle front and rear",
        "vehicle_world_displacement_vs_heading_zh": "anchored displacement direction compared with vehicle heading and route tangent",
        "vehicle_motion_direction": "forward/reverse/turned_then_forward/static/uncertain/not_applicable",
        "unexplained_reverse_motion": "yes/no/uncertain/not_applicable",
        "subject_relative_change_zh": "pose, articulation, contact, support, or world-anchor-relative change; screen displacement alone is invalid",
        "unchanged_coupled_details_zh": "unchanged smoke, exhaust, splash, shadow, carried object, clothing fold, or contact geometry that indicates copy-paste freezing",
        "accumulated_change_zh": "task-relevant change over the full sequence, or from pre-occlusion to reappearance when applicable",
        "evidence_zh": "visible progress or lack of progress across the full video",
        "final_score_cap_applied": "number or null",
    },
    "oe_instruction_following_check": {
        "applicable": "yes for out-of-sight OE, otherwise no",
        "verdict": "pass/partial/fail/not_applicable",
        "instruction_following_score": "1 for pass or partial, 0 for fail, null when not applicable",
        "meaningful_requested_trajectory_progress": "yes/partial/no/not_applicable",
        "revisit_required": "yes/no",
        "starting_pose_revisited": "yes/partial/no/not_applicable",
        "observed_action_zh": "camera or controlled-agent action only",
        "trajectory_evidence_zh": "chronological trajectory evidence without identity or visual-content matching",
        "failure_reason_zh": "concise trajectory-only reason when partial or fail, otherwise empty",
    },
    "oe003_ink_deposition_check": {
        "applicable": "yes/no",
        "persistent_new_ink": "yes/no/uncertain",
        "ink_change_type": "new stroke/extension/thickening/darkening/enlargement/none/uncertain",
        "same_anchored_paper_region_compared": "yes/no",
        "initial_ink_state_zh": "ink state before the observed marking change",
        "change_sequence_zh": "chronological ink deposition or lack of change without artificial stage boundaries",
        "resulting_ink_state_zh": "latest resulting ink state after the observed process",
        "hand_or_pen_motion_without_ink_change": "yes/no",
        "evidence_zh": "specific persistent paper-state change or lack of it",
    },
    "oe_productive_action_check": {
        "applicable": "yes/no",
        "action_type": "writing/drawing/coloring/painting/cutting/assembling/other",
        "tool_and_target": "named tool and same tracked target surface or workpiece",
        "persistent_result_created": "yes/partial/no",
        "result_recognizable_and_intentional": "yes/partial/no",
        "tool_contact_causes_local_change": "yes/partial/no",
        "action_result_temporally_coherent": "yes/partial/no",
        "prompt_named_requirement": "word/symbol/subject/color/region/outcome/not_specified",
        "result_matches_named_requirement": "yes/partial/no/not_applicable",
        "result_later_disappears_or_resets": "yes/no/uncertain",
        "visible_reversal_explanation": "erasing/covering/removal/other/none/not_applicable",
        "productive_action_quality_level_1_to_5": "integer 1 to 5",
        "evidence_zh": "chronological contact, produced-result, coherence, alignment, and persistence evidence",
    },
    "gc_dynamicity_check": {
        "meaningful_action_progress": "yes/partial/no",
        "static_or_near_static": "yes/no",
        "ineffective_repetition": "yes/no",
        "evidence_zh": "visible camera/agent progress or lack of progress across the full video",
        "final_score_gate_applied": "number or null",
    },
    "gc_appearance_stability_check": {
        "applicable": "yes/no",
        "tracked_objects_or_surfaces": ["named listed objects or surfaces actually compared"],
        "correspondence_anchors": ["at least two anchors for each non-continuously tracked comparison"],
        "visible_intervals": ["exact adjacent sampled-frame or reappearance intervals inspected"],
        "before_developing_after_checkpoints": [
            {
                "surface": "localized same tracked surface",
                "before_frame": "sampled frame number",
                "developing_frame": "sampled frame number",
                "after_frame": "sampled frame number",
                "observed_change_zh": "specific intrinsic appearance change",
            }
        ],
        "intrinsic_color_drift": "none/possible/verified",
        "material_or_texture_drift": "none/possible/verified",
        "generated_noise_artifacts": "none/possible/verified",
        "noise_type": "none/colored_speckles/blotches/crawling_dots/granular_corruption/checker_patches/flickering_pixels/other",
        "allowed_visual_explanation": "lighting/shadow/exposure/perspective/occlusion/motion_blur/wetness/compression/new_surface/none",
        "evidence_zh": "temporal same-surface evidence, or why an apparent change is allowed",
    },
    "if_subject_motion_check": {
        "subject_expected_to_move": "yes/no",
        "meaningful_subject_motion": "yes/partial/no",
        "static_or_near_static": "yes/no",
        "camera_or_background_motion_only": "yes/no",
        "post_action_static_tail": "yes/no",
        "static_tail_first_frame": "sampled frame number or null",
        "static_tail_fraction_of_video": "number from 0 to 1",
        "post_action_static_penalty": "always 0; post-action static tails are diagnostic only",
        "evidence_zh": "visible main-person motion progress or full-video inactivity",
        "final_score_gate_applied": "number or null",
    },
    "if_instruction_following_check": {
        "applicable": "yes for third-person IF, otherwise no",
        "perspective": "third-person/first-person/other",
        "verdict": "pass/partial/fail/not_applicable",
        "instruction_following_score": "1 for pass or partial, 0 for fail, null when not applicable",
        "prompt_directed_forward_progress": "yes/partial/no/not_applicable",
        "camera_or_background_motion_only": "yes/no/not_applicable",
        "observed_action_zh": "what the controlled subject actually does",
        "trajectory_evidence_zh": "chronological evidence for prompt-directed progress or its absence",
        "failure_reason_zh": "concise reason when partial or fail, otherwise empty",
    },
    "if_collision_boundary_checklist": {
        "applicable": "yes/no",
        "interaction_opportunity_reached": "yes/partial/no",
        "observed_outcome": "blocked_stop/detour/redirected_contact/stepped_or_climbed_onto/contacted_and_continued/avoided/unresolved/solid_penetration/no_motion/other",
        "solid_interpenetration": "yes/no/uncertain",
        "support_after_contact": "plausible/implausible/not_applicable/uncertain",
        "boundary_response_plausible": "yes/partial/no",
        "evidence_zh": "adjacent-frame evidence distinguishing reasonable contact, occlusion, and solid penetration",
    },
    "if_target_boundary_stability_check": {
        "target_boundary": "named wall, door, fence, cliff edge, vegetation, water edge, furniture, or other intended contact object",
        "target_type": "solid_boundary/flexible_contact_surface/social_or_destination/not_applicable/uncertain",
        "tracked_before_contact": "yes/no/uncertain",
        "remained_present_until_trigger": "yes/no/uncertain",
        "observed_trigger": "contact/proximity mechanism/applied force/none/uncertain/not_applicable",
        "unsupported_change": "none/opened/disappeared/retracted/transformed/new_path_created/other",
        "interaction_opportunity_preserved": "yes/no/uncertain",
        "evidence_zh": "adjacent-frame chronology showing whether the target stayed stable or changed before any plausible trigger",
    },
    "if_support_proxy_check": {
        "direct_support_interface_visible": "yes/partial/no",
        "proxy_evidence_observed": ["torso_or_head_bob", "weight_transfer", "joint_motion", "rider_bounce", "stable_mounted_height", "gait_synchronized_translation"],
        "proxy_supports_expected_locomotion": "yes/partial/no",
        "evidence_zh": "adjacent-frame body-motion evidence used when feet, hooves, wheels, mount, or contact interface is not visible",
    },
    "subject_identity_check": {
        "applicable": "yes",
        "tracked_subject": "named persistent person, animal, vehicle, robot, boat, tool, liquid, gripper, manipulated object, or other main entity",
        "same_entity_throughout": "yes/partial/no",
        "stable_identity_attributes": ["clothing", "body_proportions", "face_or_hair", "persistent_equipment", "colors", "materials", "textures", "surface_appearance"],
        "identity_failure": "none/color_drift/material_melting/texture_drift/surface_repainting/noise_speckles/blotches/crawling_artifacts/morphing/replacement/swap/duplication/fusion/splitting/contradictory_reappearance",
        "evidence_zh": "chronological identity and appearance evidence while allowing explained pose, scale, perspective, lighting, shadow, blur, wetness, physical deformation, prompt-required evolution, and occlusion changes",
    },
    "subject_identity_eligibility_check": {
        "core_process": "IF_interaction_quality/OE_evolution",
        "core_process_level": "number from 1 to 5",
        "meaningful_motion_or_evolution": "yes/partial/no",
        "contact_or_support_demonstrated": "yes/partial/no/not_applicable",
        "identity_eligible_for_normal_weighting": "yes/no",
        "final_score_cap_applied": "the IF interaction quality level, OE evolution cap, or null",
        "evidence_zh": "why stable identity can or cannot contribute after the core process gate",
    },
    "if_interaction_quality_check": {
        "interaction_quality_level_1_to_5": "integer 1, 2, 3, 4, or 5 using the IF interaction rubric",
        "interaction_opportunity_reached": "yes/partial/no",
        "physical_response_observed": "yes/partial/no",
        "core_failure_zh": "most important visible physical defect or none",
        "positive_evidence_zh": "visible motion or interaction evidence supporting levels 2-5",
        "evidence_zh": "concise full-interaction chronological justification without artificial stage boundaries",
        "final_score_cap_applied": "same integer as interaction_quality_level_1_to_5",
    },
    "summary_zh": "one concise sentence",
}


def applicable_questions(question_item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return questions that contribute to the normalized non-task score."""
    return [
        question
        for question in question_item.get("questions", [])
        if question.get("category") != "task_specific"
        and question.get("applicable") is not False
        and float(question.get("weight", 1) or 0) != 0
    ]


def scope_specific_instructions(
    video_item: dict[str, Any], question_item: dict[str, Any]
) -> tuple[str, ...]:
    """Return case/group rules that take precedence over generic scoring guidance."""
    requirements = question_item.get("case_visibility_requirements", {})
    instructions: list[str] = []
    if requirements.get("relative_position_scope") == "existing_object_relationships_only":
        instructions.extend(
            (
                "For relative_position in this case, score only mutual world-space distances, attachment points, ordering, and local arrangement among already established co-visible or consistently identifiable objects. Camera trajectory, screen position, framing discontinuity, return timing, and later camera over-travel are outside this category.",
                "A subject abruptly leaving or returning to the image because of camera motion is not itself a relative-position failure. Require visible evidence that existing objects changed their mutual spatial relationship before lowering relative_position.",
            )
        )
    if requirements.get("ignore_post_completion_camera_overtravel"):
        instructions.append(
            "For this case, do not apply post_completion_adjustment for continued camera travel after returning to an earlier view; set that adjustment to 0 unless a separate non-camera failure explicitly covered by the scored categories occurs."
        )
    if requirements.get("mandatory_initial_later_inventory_comparison"):
        instructions.extend(
            (
                "This case requires an explicit initial-versus-later inventory comparison for the listed continuously visible objects. Choose checkpoints from the prompt-defined action structure; for a loop/revisit, compare before departure and after return, using intermediate observations only where correspondence is established. Do not replace this with a generic statement that the scene looks stable.",
                "A category score of 5 is allowed only when its evidence itemizes the required object counts or structures and confirms them across checkpoints. Extra overlapping structures, duplicated props, or changed counts within a continuously visible anchored group are failures, not newly revealed content or parallax.",
            )
        )
    if requirements.get("adversarial_duplicate_check"):
        instructions.extend(
            (
                "Before awarding identity_id or relative_position above 3, actively try to falsify consistency: inspect tabletop edges, count every independently rendered chair, and distinguish a physical object from its glass reflection using support/contact and occlusion. Check whether a second bowl, prop, table panel, or furniture instance exists simultaneously rather than assuming it is reflection or parallax.",
                "For each suspicious extra instance, state which original object it corresponds to and cite continuous motion or support geometry. If no defensible one-to-one correspondence exists, treat it as duplication or replacement and lower the relevant score. Do not resolve ambiguity in favor of a perfect score.",
            )
        )
    if requirements.get("mandatory_reappearance_component_comparison"):
        instructions.extend(
            (
                "For this case, relative_position must explicitly compare the listed secondary component before it leaves view and after it reappears. Check its support attachment point, support length and angle, and distances to the primary structure; generic claims of stable component layout are insufficient.",
                "Ignore a camera jump by itself, but do not use that exemption to forgive a component that reappears at a different attachment point or distance. A changed support geometry is direct object-to-object relative-position evidence.",
            )
        )
    if requirements.get("component_count_visibility_check"):
        instructions.extend(
            (
                "Count each initially established structural component at prompt-relevant checkpoints. For a loop/revisit, compare the anchored state before departure with the stable returned state. Rotation can change projected angles but cannot reduce component count or make an attached component terminate in a visible unobstructed region.",
                "Before excusing a missing component as off-screen or occluded, verify that the full expected region is actually outside the frame or blocked by visible geometry. If the attachment area and surrounding region are visible and empty, score disappearance or count loss as identity failure.",
            )
        )
    if requirements.get("main_sail_rigidity_check"):
        instructions.append(
            "Treat each main sail as a rigid straight lattice component. Across rotation, verify stable arm length, width, straightness, side rails, and ladder-like crossbar topology. Visible bending, kinking, collapse, broadening into a solid board, or topology change is structural identity failure, not rotation blur or perspective."
        )
    if requirements.get("evaluation_scope") == "initial_reference_objects_only":
        instructions.extend(INITIAL_REFERENCE_ONLY_INSTRUCTIONS)
    elif requirements.get("evaluation_scope") == "continuous_foreground_full_background":
        instructions.extend(CONTINUOUS_FOREGROUND_FULL_BACKGROUND_INSTRUCTIONS)

    task_id = str(video_item.get("task") or question_item.get("task_id") or "")
    group = str(video_item.get("group") or "")
    if group == "IF" or task_id.startswith("IF"):
        instructions.extend(IF_SCORING_INSTRUCTIONS)
    if group == "OE" or task_id.startswith("OE"):
        instructions.extend(OE_SCORING_INSTRUCTIONS)
    if group == "GC" or task_id.startswith("GC"):
        instructions.extend(GC_SCORING_INSTRUCTIONS)
    requested_prompt = str(question_item.get("prompt") or "").lower()
    sub_category = str(question_item.get("sub_category") or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    is_gc = group == "GC" or task_id.startswith("GC")
    is_out_of_sight_oe = (
        (group == "OE" or task_id.startswith("OE"))
        and "outofsight" in sub_category
    )
    has_loop_or_return = any(
        token in requested_prompt
        for token in (
            "return", "turn back", "come back", "walk back", "circle back",
            "original view", "original position", "original direction", "360",
        )
    )
    if has_loop_or_return and (is_gc or is_out_of_sight_oe):
        instructions.extend(ROTATION_FINAL_STATE_INSTRUCTIONS)
    return tuple(instructions)


def build_scoring_context(
    video_item: dict[str, Any],
    question_item: dict[str, Any],
    frames_count: int,
    *,
    fps: int = DEFAULT_FPS,
    sampling_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a serializable summary of everything Gemini may use for scoring."""
    questions = applicable_questions(question_item)
    categories = [question.get("category") for question in questions]
    weights = {
        question.get("category"): float(question.get("weight", 1) or 1)
        for question in questions
    }
    special_instructions = scope_specific_instructions(video_item, question_item)
    return {
        "metric": "WorldModelBenchMark non-task-specific video quality",
        "video_metadata": {
            "model": video_item.get("model"),
            "task_id": video_item.get("task") or question_item.get("task_id"),
            "group": video_item.get("group"),
            "view": video_item.get("view"),
            "requested_prompt": question_item.get("prompt"),
            "action_sequence": question_item.get("action_sequence"),
            "action_sequence_steps": question_item.get("action_sequence_steps"),
            "image_caption": video_item.get("caption")
            or question_item.get("image_caption"),
            "status": video_item.get("status"),
        },
        "structured_questions": questions,
        "case_visibility_requirements": question_item.get(
            "case_visibility_requirements", {}
        ),
        "case_specific_evaluation_policy": question_item.get(
            "case_specific_evaluation_policy", {}
        ),
        "evaluation_policy": question_item.get(
            "non_task_specific_evaluation_policy", GENERIC_POLICY
        ),
        "scope_specific_instructions": list(special_instructions),
        "scoring_scope": {
            "categories": categories,
            "weights": weights,
            "score_scale": [SCORE_MIN, SCORE_MAX],
            "excluded": ["task_specific", "applicable=false", "weight=0"],
        },
        "sampling": sampling_metadata
        or {
            "strategy": "legacy uniform full-video sampling",
            "primary": {
                "fps": fps,
                "sample_interval_seconds": 1 / fps,
                "frames_count": frames_count,
            },
            "chronological_order": True,
            "reference_image_role": "initial scene/style context only, if provided",
        },
    }


def build_scoring_prompt(
    video_item: dict[str, Any],
    question_item: dict[str, Any],
    frames_count: int,
    *,
    fps: int = DEFAULT_FPS,
    sampling_metadata: dict[str, Any] | None = None,
) -> str:
    """Render the canonical Gemini prompt used by the batch video scorer."""
    context = build_scoring_context(
        video_item,
        question_item,
        frames_count,
        fps=fps,
        sampling_metadata=sampling_metadata,
    )
    special_instructions = scope_specific_instructions(video_item, question_item)
    instructions = "\n".join(f"- {instruction}" for instruction in SCORING_INSTRUCTIONS)
    special_section = ""
    if special_instructions:
        rendered = "\n".join(f"- {instruction}" for instruction in special_instructions)
        special_section = (
            "\n\nCase/group-specific instructions (these override any conflicting generic "
            "instruction above):\n"
            f"{rendered}"
        )
    invalid_findings = context.get("case_visibility_requirements", {}).get(
        "known_invalid_findings", []
    )
    invalid_findings_section = ""
    if invalid_findings:
        rendered = "\n".join(f"- {finding}" for finding in invalid_findings)
        invalid_findings_section = (
            "\n\nAuthoritative known-invalid findings for this case:\n"
            f"{rendered}\n"
            "MANDATORY OUTPUT CHECK: Before returning JSON, scan every category score, evidence, "
            "background statement, correspondence check, adjustment, and summary. If any statement "
            "semantically repeats a known-invalid finding above, delete that evidence and its penalty, "
            "then recompute the base and final scores. An output that uses any known-invalid finding, "
            "even with different wording, is invalid."
        )
    return (
        "You are evaluating a generated world-model video using a comparable "
        "1-5 non-task-specific quality scale.\n\n"
        "Scoring context:\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Scoring instructions:\n"
        f"{instructions}{special_section}{invalid_findings_section}\n\n"
        "Return JSON only, matching this schema:\n"
        f"{json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}"
    )


__all__ = [
    "DEFAULT_FPS",
    "GENERIC_POLICY",
    "GC_SCORING_INSTRUCTIONS",
    "CONTINUOUS_FOREGROUND_FULL_BACKGROUND_INSTRUCTIONS",
    "INITIAL_REFERENCE_ONLY_INSTRUCTIONS",
    "IF_SCORING_INSTRUCTIONS",
    "OE_SCORING_INSTRUCTIONS",
    "ROTATION_FINAL_STATE_INSTRUCTIONS",
    "OUTPUT_SCHEMA",
    "SCORING_INSTRUCTIONS",
    "applicable_questions",
    "build_scoring_context",
    "build_scoring_prompt",
    "scope_specific_instructions",
]
