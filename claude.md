# MASTER PROMPT — AssemblyVision
## Fully Local AI-Powered Work Instruction Monitoring Platform

You are an experienced senior software engineer, computer vision engineer, AI systems architect and UI/UX designer.

Your task is to design, develop, test and deliver a complete, professional, fully functional local application named **AssemblyVision**.

AssemblyVision is a proof-of-concept platform that uses locally running multimodal AI models and two cameras to monitor physical work instructions in real time.

It must recognize physical objects, observe changes in their position or assembly state, determine whether predefined work steps have been completed, and automatically update a visual checklist.

The application will be demonstrated to colleagues, innovation teams and stakeholders as an example of practical, privacy-friendly AI in industrial environments.

**This must be a real working application, not a frontend mockup or a simulation disguised as AI.**

All operator-facing interface text must be in Dutch. Code, technical documentation and developer comments may be written in English.

---

# 1. Hardware and runtime environment

The initial target hardware is:

- Computer: Apple MacBook Air 15-inch (2024)
- Processor: Apple M3
- Memory: 24 GB unified memory
- Operating system: macOS Tahoe 26.7.1
- Camera 1: Elgato Facecam 4K
- Camera 2: Elgato Facecam 4K
- Local inference server: Ollama
- Initial preferred model: `qwen3-vl:4b-instruct`

Ollama is already being installed and models may have been downloaded.

Do not assume any specific model is installed. Inspect the local environment and discover available models automatically.

The MacBook Air is fanless, so prioritize controlled inference scheduling, reasonable memory usage and thermal stability.

The final application must support fully offline operation after installation.

Do not send camera frames, images, prompts, inference results or workflow information to external services.

Development with Claude Code may use the internet, but runtime AI processing must be fully local.

---

# 2. Main objectives

The application must support the following core scenarios:

1. Show two live camera feeds observing the same work area.
2. Allow an operator to select a work instruction containing several physical steps.
3. Analyze real camera frames using a locally installed vision-language model.
4. Identify visible objects and their relationships.
5. Observe changes in the physical assembly state.
6. Determine whether the current instruction's observable completion criteria are satisfied.
7. Automatically mark confirmed steps as completed.
8. Prevent incorrect or unverified steps from being automatically completed.
9. Provide clear visual feedback when an instruction is incomplete or uncertain.
10. Allow users to switch between locally installed AI models.
11. Allow users to adjust camera FPS, image sampling and AI inference settings.
12. Provide a visual workflow editor for creating additional work instructions.
13. Display inference performance, recognition decisions and activity history.
14. Offer simulation mode separately from real AI monitoring.

The application should be visually impressive, technically credible and straightforward to operate during a live demonstration.

---

# 3. Technology stack

Use the following architecture unless there is a compelling technical reason to change it.

## Backend

- Python 3.11 or newer.
- FastAPI.
- OpenCV for camera capture.
- Ollama local API for model inference.
- Pydantic for structured schemas.
- WebSockets for real-time status events.
- SQLite for local activity history and configuration where appropriate.
- Async processing and controlled worker execution.
- Modular services for camera handling, inference, workflows and logging.

## Frontend

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- Lucide icons.
- A lightweight charting library when useful.

Use a consistent and maintainable component architecture.

Avoid unnecessary dependencies.

Do not introduce Docker, MCP servers, cloud services, hosted databases or authentication systems unless necessary.

The application should launch with one simple local startup command or script.

---

# 4. Visual design and user experience

Create a premium industrial AI monitoring interface.

The visual style should feel like a real, modern software product rather than an experimental developer dashboard.

Design inspiration:

- Professional industrial monitoring software.
- Modern mission-control dashboards.
- Clean, sophisticated SaaS applications.
- Minimal, high-quality data visualizations.

Use:

- Dark charcoal or deep navy backgrounds.
- Subtle surfaces and borders.
- Refined typography.
- High information density without clutter.
- Consistent spacing.
- Smooth and restrained animations.
- Clear status colors.
- Excellent contrast and readability.

Status colors:

- Green: completed.
- Blue: active or monitoring.
- Amber: uncertain or awaiting verification.
- Red: incorrect or problematic.
- Neutral gray: pending.

The application should feel professional enough to present to management.

Avoid excessive gradients, decorative AI imagery and unnecessary interface complexity.

Optimize the dashboard for a 15-inch MacBook Air screen.

The two live camera feeds and the active instruction should remain immediately visible.

Use responsive layouts where needed.

---

# 5. Application navigation

Create the following main application sections:

**Dashboard**

Live camera monitoring, active work instructions, real-time AI observations and progress.

**Werkinstructies**

Browse, create, edit, duplicate, activate and delete workflows.

**AI Playground**

Manually test vision models against camera frames, inspect recognition results and compare models.

**Prestaties**

Monitor inference latency, camera FPS, model performance and benchmarking results.

**Instellingen**

Configure cameras, AI models, processing settings and local storage preferences.

Keep the primary navigation compact.

---

# 6. Main dashboard

The dashboard should include:

## Header

Display:

- AssemblyVision logo.
- Application name.
- Active workflow name.
- AI connection indicator.
- Selected AI model.
- Number of connected cameras.
- Monitoring status.
- Settings access.

## Camera monitoring area

Display two live video streams.

Camera 1:

**Bovenaanzicht**

Camera 2:

**Zijaanzicht**

Each camera view should contain:

- Live video preview.
- Camera name.
- Connection indicator.
- Actual FPS.
- Active resolution.
- Expand/fullscreen action.
- Optional AI analysis overlay.
- Capture-frame button.

The UI must handle camera disconnections gracefully.

Allow single-camera operation if only one camera is connected.

A missing camera must never cause the entire application to crash.

## Work instruction panel

Show the active workflow as an interactive checklist.

Each instruction contains:

- Step number.
- Title.
- Description.
- Status.
- Completion indicator.
- Timestamp after confirmation.
- Optional warning or explanation.

Possible states:

- Wachten
- Actief
- Analyseren
- Controleren
- Voltooid
- Onzeker
- Afwijking gedetecteerd

Display overall progress as a percentage and progress bar.

When a step is confirmed, animate the completion indicator and advance to the next instruction.

## AI observation panel

Display what the AI actually observes.

Examples:

"De bout is zichtbaar uit de montageplaat verwijderd."

"De sluitring bevindt zich naast de bout, maar is nog niet om de bout geplaatst."

"Onvoldoende visueel bewijs om stap 2 te bevestigen."

The system must distinguish between:

1. Raw visual observations.
2. Model interpretation.
3. Workflow engine decision.

Never show an AI-generated assumption as an established fact.

Display the originating camera or cameras where applicable.

## Activity log

Display timestamped events.

Examples:

- 10:42:01 — Monitoring gestart.
- 10:42:03 — Camera 1 verbonden.
- 10:42:03 — Camera 2 verbonden.
- 10:42:04 — AI-model geladen.
- 10:42:08 — Bout zichtbaar gedetecteerd.
- 10:42:14 — Stap 1 visueel bevestigd.
- 10:42:15 — Stap 2 geactiveerd.
- 10:42:22 — Onvoldoende bewijs voor stap 2.

Make the log scrollable and easy to inspect.

---

# 7. Camera management

Support two Elgato Facecam 4K webcams.

Because both cameras are the same model, camera index ordering may change when devices are reconnected.

Implement camera discovery and a persistent logical camera assignment mechanism.

Allow the operator to assign connected cameras to:

- Camera 1 — Bovenaanzicht.
- Camera 2 — Zijaanzicht.

Where stable hardware identifiers are unavailable, provide an easy reassignment interface with camera previews.

Use macOS-compatible camera acquisition.

Investigate AVFoundation or OpenCV backends where appropriate.

Avoid unnecessary camera initialization conflicts.

Support:

- Camera discovery.
- Start/stop capture.
- Resolution selection.
- FPS selection.
- Live FPS measurement.
- Camera disconnection recovery.
- Snapshot capture.
- Optional preview mirroring.
- Optional rotation if useful.

Prefer native camera resolutions and frame rates rather than assuming every combination is supported.

The initial configuration should be 1080p at 30 FPS.

Where supported, allow higher capture frame rates, including 60 FPS.

Verify actual device capabilities and report unsupported configurations clearly.

Keep camera capture independent of AI inference.

---

# 8. Adjustable FPS and image-processing pipeline

Implement a configurable performance panel.

The operator must be able to change important performance parameters directly from the UI, without modifying source code.

Provide:

### Camera capture FPS

Configurable options such as:

- 5 FPS.
- 10 FPS.
- 15 FPS.
- 24 FPS.
- 30 FPS.
- 60 FPS.

Only apply settings supported by the selected camera configuration.

### Frame sampling FPS

Allow 1–10 FPS.

Frame sampling controls how frequently fresh frames are selected for potential downstream analysis.

Do not interpret sampling FPS as the number of model calls per second.

Use a bounded latest-frame buffer.

Discard obsolete frames.

### AI inference interval

Allow a configurable minimum interval between AI inference requests, initially 1–10 seconds.

Default to 3 seconds.

Implement single-flight inference:

- Only one active inference request.
- No overlapping requests.
- No growing inference queue.
- Drop outdated analysis opportunities.
- Wait until the previous inference is finished before scheduling another eligible request.

If inference takes longer than the configured interval, the actual frequency must be lower and correctly reported.

### Image input resolution

Provide selectable maximum image dimensions:

- 384 px.
- 512 px.
- 768 px.
- 1024 px.

Preserve aspect ratio.

Use 768 px as the initial inference width, subject to practical testing.

### Camera input selection

Allow:

- Camera 1 only.
- Camera 2 only.
- Both cameras.

When both cameras are selected, send their current images as part of the same logical analysis, if the selected model supports multiple image inputs.

If a model does not support the requested configuration, provide a clear warning or compatible fallback.

Do not silently substitute fabricated data.

### Optional motion optimization

Consider lightweight OpenCV frame-difference or motion detection to reduce unnecessary inference requests.

This is an optional optimization, not a requirement for the initial version.

It must not prevent the system from recognizing an already-completed static state.

---

# 9. Local AI model management

**This is an essential requirement.**

The operator must be able to switch between different locally installed AI models directly from the application interface.

Do not hardcode the application to Qwen3-VL.

Use Ollama as a configurable inference backend.

Default endpoint:

`http://localhost:11434`

## Model discovery

On application startup:

1. Check whether Ollama is running.
2. Query the installed model list using the local Ollama API.
3. Display available model names.
4. Discover model metadata and capabilities where supported.
5. Identify models that support image input.
6. Prefer showing compatible vision-language models for live recognition.

For unsupported or unknown capabilities, provide a testable status rather than assuming compatibility.

## Model selection

Implement a dropdown:

**AI-model**

Example options, only if actually installed:

- qwen3-vl:4b-instruct
- qwen3-vl:8b
- Other compatible local vision models

These are examples, not a fixed list.

The dropdown must reflect the actual installed models.

Allow switching models without restarting the application.

When switching:

- Pause new inference scheduling.
- Handle any in-flight inference safely.
- Load or initialize the newly selected model.
- Confirm that image inference works.
- Reset temporary confirmation counters.
- Resume monitoring only after successful activation.
- Show clear loading and error states.

Do not mark previously confirmed workflow steps as newly observed by the new model.

Allow the user to reset the workflow when changing models.

## Model information

Show useful metadata where available:

- Model name.
- Model size.
- Model family.
- Parameter count.
- Quantization information.
- Vision compatibility.
- Current load status.
- Last measured inference latency.

Do not invent missing metadata.

## Model controls

Provide:

- Refresh installed models.
- Select active model.
- Check model availability.
- Test model with a snapshot.
- View last inference result.
- View latency statistics.

Optionally include an interface to download additional Ollama models, but only as a user-initiated action, with explicit download sizes and progress reporting where available.

Do not automatically download large models.

## Model configuration

Support adjustable:

- Temperature.
- Context length, within practical hardware limits.
- Output token limit.
- Image input size.
- Inference timeout.
- Optional keep-alive setting.

Provide safe defaults and explain advanced settings in the interface.

Do not expose every low-level parameter on the main dashboard.

---

# 10. Real visual recognition

The application must actually analyze captured camera images.

Use Ollama's supported multimodal image input format and structured-output capabilities.

Create a dedicated inference service that accepts:

- Active model.
- Current workflow.
- Current step.
- Relevant completion criteria.
- One or two camera frames.
- Optional previous observations or reference images.

Return a validated structured observation.

Example output schema:

```json
{
  "step_id": "step_2",
  "status": "incomplete",
  "visible_objects": [
    {
      "name": "bolt",
      "visible": true
    },
    {
      "name": "washer",
      "visible": true
    }
  ],
  "observed_relationships": [
    "washer next to bolt"
  ],
  "evidence": "The washer is visible next to the bolt but is not positioned around it.",
  "source_cameras": [1, 2],
  "uncertain": false
}
```

Use Pydantic to validate the response.

Allowed observation statuses:

- completed
- incomplete
- uncertain

Reject malformed or inconsistent observations.

If the model does not return valid structured output, do not automatically complete the instruction.

## Recognition rules

The model should be instructed to:

- Describe only visually observable facts.
- Identify relevant objects.
- Identify relevant spatial relationships.
- Compare the current observed state with the expected completion state.
- Avoid guessing about hidden objects or occluded components.
- Identify insufficient visibility.
- Report uncertainty explicitly.
- Avoid claiming mechanical properties that cannot be verified visually.

For example, the model may recognize that a wing nut is installed but cannot necessarily verify tightening torque.

Do not present visual completion as proof of mechanical safety.

---

# 11. Workflow verification engine

Implement a deterministic workflow state machine.

The AI model generates observations.

The workflow engine decides whether a step can be completed.

The model must never directly change workflow states.

## Verification requirements

1. Only the active step can automatically progress.
2. A single positive observation is insufficient.
3. Require three consecutive successful observations by default.
4. Make this number adjustable.
5. Reset the counter on contradictory evidence.
6. Handle uncertain observations conservatively.
7. Reject out-of-sequence completion.
8. Track the exact evidence used.
9. Record the verification timestamp.
10. Support manual confirmation and reset.

Do not treat three identical model outputs from the same stale frame as independent evidence.

Require fresh captured frames for successive confirmations.

## State changes and temporal information

Where useful, compare images captured before and after a physical change.

For example:

Initial state:
Bolt is inserted in the plate.

Updated state:
Bolt is visibly removed.

Result:
Removal is visually supported.

However, recognize the limitation that a vision-language model may not reliably infer every physical action.

Focus on observable state transitions.

## Manual intervention

Allow the operator to:

- Confirm a step manually.
- Reject a proposed completion.
- Reset the active step.
- Restart the entire workflow.

Manual confirmations must be explicitly recorded as manual actions, not AI detections.

## Errors and unexpected conditions

Examples:

- Washer missing.
- Bolt still inserted.
- Wrong component placed.
- Work area obstructed.
- Camera image too dark.
- No clear view of the active assembly.

Distinguish between:

- Confirmed deviations.
- Suspected deviations.
- Insufficient visual evidence.

Avoid presenting unsupported assumptions as definitive errors.

---

# 12. Initial demonstration workflows

Implement two editable example workflows.

## Workflow A — Bolt Assembly

Dutch title:

**Montagecontrole — Bout en sluitring**

Steps:

### Step 1 — Verwijder de bout

Instruction:
"Verwijder de bout uit de montageplaat en leg deze zichtbaar op het werkvlak."

Completion:
The bolt is visibly removed from the mounting plate.

### Step 2 — Plaats de sluitring

Instruction:
"Plaats de sluitring om de verwijderde bout."

Completion:
The washer is visibly positioned around the bolt.

### Step 3 — Monteer de bout

Instruction:
"Plaats de bout terug in de montageplaat en bevestig de vleugelmoer."

Completion:
The bolt is visibly reinserted and the wing nut is visibly installed.

Do not infer tightening torque from visual appearance.

## Workflow B — Object Placement

Dutch title:

**Montagecontrole — Onderdelen positioneren**

Create a simpler workflow involving three clearly distinguishable colored components.

For example:

1. Place a red component in position A.
2. Place a blue component in position B.
3. Place a green component in position C.

The positions should be visibly marked.

This workflow is intended for initial testing of recognition accuracy, camera angles and completion logic.

Both workflows must use the same underlying workflow engine.

---

# 13. Visual workflow editor

Create a user-friendly workflow editor.

The user should be able to create a new instruction without modifying source code.

Support:

- Create workflow.
- Edit workflow.
- Duplicate workflow.
- Delete workflow.
- Rename workflow.
- Add steps.
- Remove steps.
- Reorder steps.
- Edit instruction text.
- Define expected visible objects.
- Define observable completion conditions.
- Define optional deviation conditions.
- Set required confirmation count.
- Save and activate workflows.

The editor should support a simple mode and an advanced mode.

## Simple mode

User enters:

- Workflow name.
- Step title.
- Instruction.
- What must be visible when the step is complete.

## Advanced mode

User can configure:

- Object expectations.
- Spatial relationships.
- State transitions.
- Evidence requirements.
- Camera preferences.
- Verification count.
- Optional reference images.

Store workflows locally in a structured, versioned format such as JSON or YAML.

Validate workflow definitions before activation.

Allow export and import of workflow definitions.

Do not allow arbitrary executable code in imported workflow configurations.

---

# 14. AI Playground

Build a dedicated environment for experimenting with local vision models.

This is important for development and live demonstrations.

The user must be able to:

1. Select a locally installed vision model.
2. Select camera 1, camera 2 or both.
3. Capture current frames.
4. Enter a custom visual recognition question.
5. Execute a local inference request.
6. View the model response.
7. Inspect structured output.
8. See inference duration.
9. Compare the response with a second model.

Example questions:

- "Welke onderdelen liggen op tafel?"
- "Is de bout verwijderd uit de montageplaat?"
- "Waar bevindt de sluitring zich ten opzichte van de bout?"
- "Is de vleugelmoer zichtbaar gemonteerd?"
- "Wat is er veranderd tussen deze twee opnames?"

Provide a side-by-side model comparison.

Example:

Model A: qwen3-vl:4b-instruct

Model B: another locally installed vision model.

Display:

- Model name.
- Input images used.
- Prompt.
- Response.
- Duration.
- Whether output validation succeeded.

Use exactly the same input snapshots and task prompt for a fair comparison.

Run comparisons sequentially by default to avoid exhausting the MacBook's memory.

The AI Playground must remain independent of the active workflow state.

Testing recognition must not accidentally complete an active work instruction.

---

# 15. AI detection overlay

Implement an optional visualization layer over the camera feeds.

The overlay may show:

- Active analysis indicator.
- Detected object labels.
- Recognition state.
- Relevant textual observations.
- Visual markers where coordinates are available.

Do not fabricate bounding boxes.

Only render spatial boxes when the selected model or a dedicated detector supplies valid, correctly mapped coordinates.

The initial VLM implementation may use textual recognition without spatial boxes.

Design the system so that a future dedicated object detector, such as YOLO, can be integrated without rewriting the workflow engine.

Do not make YOLO a mandatory dependency for the initial MVP.

---

# 16. Performance dashboard

Build a dedicated performance monitoring section.

Display:

## Camera metrics

- Actual FPS for each camera.
- Resolution.
- Number of dropped frames where measurable.
- Capture status.

## Inference metrics

- Active model.
- Current analysis interval.
- Actual inference frequency.
- Last inference duration.
- Average inference duration.
- Median inference duration.
- P95 inference duration.
- Total inference requests.
- Failed inference requests.
- Skipped analysis opportunities.
- Input image resolution.
- Number of images per analysis.

## System metrics

Where reliably available:

- Application CPU usage.
- Application memory usage.
- Model process memory where observable.

Use local system APIs.

Do not invent GPU utilization or temperature measurements if macOS does not expose reliable values through supported interfaces.

## Charts

Provide:

- Inference latency over time.
- Actual inference frequency over time.
- Camera FPS over time.

Keep historical metrics bounded to avoid uncontrolled memory use.

---

# 17. Benchmark mode

Implement a configurable benchmark tool.

Purpose:

Find the best model and processing settings for the Apple M3 with 24 GB memory.

Allow comparisons of:

- Selected installed models.
- Camera 1 versus two-camera inference.
- Input resolution.
- Analysis interval.
- Inference latency.

Use saved local test snapshots so benchmark comparisons use identical input images.

Support an optional manually labeled test dataset for measuring recognition accuracy.

Do not call a model "more accurate" solely because it responds faster or produces a higher self-reported confidence score.

Separate:

- Speed measurements.
- Schema validity.
- Human-labeled recognition correctness.
- Workflow completion correctness.

Show results in a sortable table.

Allow benchmark results to be exported as CSV or JSON.

Include a clear explanation that benchmark results depend on the tested scene and hardware.

---

# 18. Simulation mode

Provide a separate, fully functional simulation mode.

Simulation mode should allow demonstrating the workflow even without cameras or Ollama.

Show a prominent:

**SIMULATIEMODUS**

indicator.

Simulated observations should pass through the same workflow state machine used in live mode.

Support:

- Simulate valid observation.
- Simulate incomplete observation.
- Simulate uncertainty.
- Simulate incorrect action.
- Reset workflow.
- Step-by-step demonstration.

Where possible, use locally supplied sample images or videos.

Never display simulated data as real camera output.

Never silently switch from real mode to simulation when Ollama fails.

The user must explicitly select simulation mode.

---

# 19. Local storage and privacy

All data must remain on the local machine.

Use SQLite or local configuration files.

Store:

- Workflow definitions.
- User preferences.
- Camera assignments.
- Inference settings.
- Workflow event history.
- Optional benchmark results.

Do not continuously store raw camera video.

Do not enable raw image retention by default.

Make optional snapshot retention clearly configurable.

Provide options to:

- Clear event history.
- Delete saved snapshots.
- Export workflow history.
- Reset application preferences.

Bind the backend to localhost by default.

Do not expose the application to the local network unless explicitly configured.

Disable external telemetry.

No application account, login or internet connection should be required.

---

# 20. Error handling and application robustness

Handle:

- Ollama not running.
- No installed vision-compatible models.
- Selected model unavailable.
- Model loading failure.
- Model-switching failure.
- Malformed inference output.
- Inference timeout.
- Camera disconnected.
- Camera permission denied.
- Camera already in use.
- Unsupported camera FPS.
- Invalid workflow configuration.
- Backend connection lost.
- Frontend temporarily disconnected.

Provide meaningful Dutch error messages.

The application must never report a workflow step as completed when the underlying evidence was not successfully verified.

Use explicit and recoverable UI states.

Keep the interface responsive even if local inference is slow.

---

# 21. Suggested software architecture

Organize the application using clear functional modules.

Example:

Backend:

- camera_manager
- frame_sampler
- inference_service
- ollama_model_manager
- observation_validator
- workflow_engine
- workflow_repository
- event_logger
- benchmark_service
- websocket_manager

Frontend:

- Dashboard
- CameraViewer
- WorkflowChecklist
- AIObservationPanel
- ActivityLog
- ModelSelector
- PerformanceControls
- WorkflowEditor
- AIPlayground
- BenchmarkDashboard
- Settings

This is conceptual guidance, not a rigid naming requirement.

Prefer maintainable boundaries between modules.

Do not put the entire backend into one file.

Do not combine AI model responses and business logic in a single large function.

---

# 22. Recommended default configuration

Use the following defaults for the initial MacBook Air deployment:

- Camera capture: 1080p, 30 FPS.
- Frame sampling: 2 FPS.
- Inference image width: 768 px.
- AI analysis interval: minimum 3 seconds.
- Images per inference: one fresh frame per active camera.
- Active model: qwen3-vl:4b-instruct if installed and compatible.
- Consecutive confirmations: 3.
- Local inference: enabled.
- Automatic step completion: enabled.
- Simulation mode: disabled.
- Snapshot retention: disabled.
- External networking: disabled.

Treat these as configurable starting values, not guaranteed performance targets.

Do not queue inference requests.

On slower models, automatically skip obsolete analysis opportunities.

Show the actual achieved analysis frequency.

---

# 23. Development and testing approach

Implement the application in logical phases.

## Phase 1 — Environment inspection

Inspect:

- Operating system.
- Python availability.
- Node.js availability.
- Ollama availability.
- Installed models.
- Camera discovery.
- Existing project files.

Do not unnecessarily reinstall existing dependencies.

Document any missing requirements.

## Phase 2 — Application foundation

Create:

- Backend structure.
- Frontend structure.
- Configuration system.
- Local API.
- WebSocket communication.
- Database or local storage.
- Startup scripts.

## Phase 3 — Professional dashboard

Build the complete dashboard with clearly labeled development test data.

Implement workflow selection, checklist rendering, status changes and event logging.

## Phase 4 — Real camera integration

Connect the actual Elgato webcams.

Verify that both can operate simultaneously.

Implement camera assignments, preview streaming and performance controls.

## Phase 5 — Real Ollama inference

Connect to Ollama.

Discover installed models.

Implement actual image inference and structured response validation.

Build the model selection interface.

Test at least one real camera snapshot with the selected model if hardware access is available.

## Phase 6 — Workflow verification

Build the deterministic state machine.

Connect observations to completion logic.

Implement multiple-confirmation verification, uncertain states and manual correction.

## Phase 7 — AI Playground

Implement custom prompts, snapshot analysis and sequential model comparisons.

## Phase 8 — Workflow editor

Implement workflow creation, editing, validation, local persistence, import and export.

## Phase 9 — Performance and benchmark tools

Implement latency statistics, configurable processing parameters, charts and benchmark comparisons.

## Phase 10 — Simulation mode

Implement explicit simulation mode and error-case demonstrations.

## Phase 11 — Final integration and testing

Test:

- Camera startup.
- Two-camera operation.
- Single-camera fallback.
- Real model inference.
- Model switching.
- Workflow progression.
- Invalid inference output.
- Incorrect action detection.
- Camera disconnection.
- Ollama shutdown.
- Simulation mode.
- Export functions.
- Application restart.
- Offline operation.

Write automated tests for the workflow engine and model-response validation.

Verify frontend production build and backend tests.

Run real hardware tests where possible.

Do not claim a feature was tested if the relevant hardware or software was inaccessible.

---

# 24. Deliverables

Deliver a working local project containing:

1. Complete React frontend.
2. Complete FastAPI backend.
3. Functional camera integration.
4. Functional Ollama model integration.
5. Automatic local model discovery and switching.
6. Real visual observation pipeline.
7. Deterministic workflow verification.
8. Configurable FPS and inference settings.
9. Workflow editor.
10. AI Playground.
11. Performance monitoring.
12. Benchmarking.
13. Explicit simulation mode.
14. Local persistence.
15. Automated tests.
16. README with setup, operation, limitations and troubleshooting.
17. A convenient startup script.

Make it easy to run locally.

Prefer one startup command that launches both backend and frontend.

Document the browser URL and how to stop the application.

---

# 25. Acceptance criteria

The application is complete when the following can be demonstrated:

**Real recognition**

Place a physical object in front of the cameras, change its position and observe the local AI model recognizing the new visual state.

**Automatic progress**

Perform the first assembly instruction correctly and see the system automatically mark the step as completed after the required confirmations.

**Error handling**

Skip an instruction or remove a required component and verify that the system does not incorrectly approve the step.

**Model switching**

Select a different locally installed vision model from the interface, have the application activate it without restarting and successfully execute a new inference request.

**FPS settings**

Change camera FPS, frame sampling and AI analysis interval and observe updated measured performance.

**Custom workflows**

Create a new three-step workflow from the interface, save it, activate it and use it for monitoring.

**AI testing**

Capture a real frame, ask a custom question and inspect the actual response from the chosen local model.

**Performance reporting**

Observe real inference timing, processing frequency and historical performance.

**Offline execution**

Disconnect from the internet and confirm that the application continues operating using locally installed resources.

**Reliability**

Disconnect a camera or stop Ollama and verify that the application handles the failure gracefully.

---

# 26. Prioritization and engineering principles

Prioritize the following outcomes, in order:

1. Genuine local computer vision inference.
2. Reliable camera handling.
3. Correct workflow state management.
4. A professional and responsive dashboard.
5. Reliable local model switching.
6. Configurable performance.
7. Workflow editing.
8. AI Playground.
9. Benchmarking.
10. Optional advanced visualizations.

If complexity becomes an issue, deliver a tested end-to-end MVP first and expand it incrementally.

Do not sacrifice real functionality in favor of appearance.

Do not implement fake inference to make the demonstration appear successful.

Do not silently omit major requirements.

Maintain a visible implementation checklist and report completed, partially completed and untested functionality accurately.

Do not stop after creating a plan or visual mockup.

**Start by inspecting the actual local development environment, checking Ollama and the available camera devices, then create the application architecture and proceed with implementation.**

Make independent, sensible engineering decisions without asking unnecessary questions.

The final result should feel like a real industrial AI software product: polished, understandable, technically honest and genuinely functional.