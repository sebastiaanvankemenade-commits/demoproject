"""The two demonstration workflows. Criteria stay in English: that is what the models were tested on."""
from .workflow_models import Workflow, WorkflowStep

BOLT_ASSEMBLY = Workflow(
    id="bolt-assembly",
    name="Montagecontrole — Bout en sluitring",
    steps=[
        WorkflowStep(
            id="remove-bolt",
            title="Verwijder de bout",
            instruction="Verwijder de bout uit de montageplaat en leg deze zichtbaar op het werkvlak.",
            completion_criterion="The bolt is visibly removed from the mounting plate and lies on the work surface.",
            expected_objects=["bolt", "mounting plate"],
            requires_transition=True,
        ),
        WorkflowStep(
            id="place-washer",
            title="Plaats de sluitring",
            instruction="Plaats de sluitring om de verwijderde bout.",
            completion_criterion="The washer is visibly positioned around the bolt.",
            expected_objects=["bolt", "washer"],
            deviation_conditions=["verkeerd onderdeel om de bout geplaatst"],
        ),
        WorkflowStep(
            id="mount-bolt",
            title="Monteer de bout",
            instruction="Plaats de bout terug in de montageplaat en bevestig de vleugelmoer.",
            completion_criterion="The bolt is visibly reinserted in the plate and the wing nut is visibly installed.",
            expected_objects=["bolt", "mounting plate", "wing nut"],
            deviation_conditions=["bout teruggeplaatst zonder sluitring"],
        ),
    ],
)

OBJECT_PLACEMENT = Workflow(
    id="object-placement",
    name="Montagecontrole — Onderdelen positioneren",
    steps=[
        WorkflowStep(
            id="place-red",
            title="Plaats het rode onderdeel",
            instruction="Plaats het rode onderdeel op positie A.",
            completion_criterion="A red component lies inside the marked position labelled A.",
            expected_objects=["red component", "position A"],
            deviation_conditions=["rood onderdeel op verkeerde positie", "verkeerd onderdeel op positie A"],
            requires_transition=True,
        ),
        WorkflowStep(
            id="place-blue",
            title="Plaats het blauwe onderdeel",
            instruction="Plaats het blauwe onderdeel op positie B.",
            completion_criterion="A blue component lies inside the marked position labelled B.",
            expected_objects=["blue component", "position B"],
            deviation_conditions=["blauw onderdeel op verkeerde positie", "verkeerd onderdeel op positie B"],
            requires_transition=True,
        ),
        WorkflowStep(
            id="place-green",
            title="Plaats het groene onderdeel",
            instruction="Plaats het groene onderdeel op positie C.",
            completion_criterion="A green component lies inside the marked position labelled C.",
            expected_objects=["green component", "position C"],
            deviation_conditions=["groen onderdeel op verkeerde positie", "verkeerd onderdeel op positie C"],
            requires_transition=True,
        ),
    ],
)

SCREW_TIGHTENING = Workflow(
    id="screw-tightening",
    name="Montagecontrole — Schroef aandraaien",
    steps=[
        WorkflowStep(
            id="tighten-screw",
            title="Draai de schroef aan",
            instruction="Draai de schroef vast in de montageplaat.",
            completion_criterion="The screw is visibly seated in the mounting plate and no hand is touching it.",
            expected_objects=["screw", "mounting plate"],
            requires_transition=True,
            expected_turns=6,
        ),
    ],
)

DEFAULT_WORKFLOWS = [OBJECT_PLACEMENT, BOLT_ASSEMBLY, SCREW_TIGHTENING]
