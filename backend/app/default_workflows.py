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
        ),
        WorkflowStep(
            id="mount-bolt",
            title="Monteer de bout",
            instruction="Plaats de bout terug in de montageplaat en bevestig de vleugelmoer.",
            completion_criterion="The bolt is visibly reinserted in the plate and the wing nut is visibly installed.",
            expected_objects=["bolt", "mounting plate", "wing nut"],
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
            requires_transition=True,
        ),
        WorkflowStep(
            id="place-blue",
            title="Plaats het blauwe onderdeel",
            instruction="Plaats het blauwe onderdeel op positie B.",
            completion_criterion="A blue component lies inside the marked position labelled B.",
            expected_objects=["blue component", "position B"],
            requires_transition=True,
        ),
        WorkflowStep(
            id="place-green",
            title="Plaats het groene onderdeel",
            instruction="Plaats het groene onderdeel op positie C.",
            completion_criterion="A green component lies inside the marked position labelled C.",
            expected_objects=["green component", "position C"],
            requires_transition=True,
        ),
    ],
)

DEFAULT_WORKFLOWS = [OBJECT_PLACEMENT, BOLT_ASSEMBLY]
