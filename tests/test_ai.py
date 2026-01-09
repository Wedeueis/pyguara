from typing import Optional
from pyguara.ai.fsm import StateMachine, State
from pyguara.ai.blackboard import Blackboard
from pyguara.ecs.entity import Entity


# Mocks
class MockState(State):
    def __init__(self, ent, bb, name):
        super().__init__(ent, bb)
        self.name = name
        self.entered = False
        self.exited = False
        self.next_state: Optional[str] = None

    def on_enter(self):
        self.entered = True

    def on_exit(self):
        self.exited = True

    def update(self, dt):
        return self.next_state


def test_blackboard():
    bb = Blackboard()
    bb.set("hp", 100)
    assert bb.get("hp") == 100
    assert bb.has("hp")
    assert bb.get("missing", 5) == 5


def test_fsm_transitions():
    entity = Entity()
    bb = Blackboard()
    fsm = StateMachine(entity, bb)

    s1 = MockState(entity, bb, "idle")
    s2 = MockState(entity, bb, "walk")

    fsm.add_state("idle", s1)
    fsm.add_state("walk", s2)

    fsm.set_initial_state("idle")
    assert fsm._current_state == s1
    assert s1.entered

    # Trigger transition
    s1.next_state = "walk"
    fsm.update(0.1)

    assert fsm._current_state == s2
    assert s1.exited
    assert s2.entered
