"""Pytest configuration and fixtures."""

import sys
import pytest
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher

# Define fake classes for Pygame types to satisfy dataclasses and inheritance
class MockColor:
    """Mock for pygame.Color."""

    def __init__(self, r=0, g=0, b=0, a=255):
        """Initialize color."""
        self.r, self.g, self.b, self.a = r, g, b, a

    def __iter__(self):
        """Allow iteration."""
        return iter((self.r, self.g, self.b, self.a))

    def normalize(self):
        """Return normalized color."""
        return (self.r/255, self.g/255, self.b/255, self.a/255)
    
class MockRect:
    """Mock for pygame.Rect."""

    def __init__(self, x=0, y=0, w=0, h=0):
        """Initialize rect."""
        self.x, self.y, self.w, self.h = x, y, w, h
        self.width, self.height = w, h
        self.centerx = x + w//2
        self.centery = y + h//2

    def collidepoint(self, x, y):
        """Mock collision check."""
        return True

@pytest.fixture
def container():
    """Provide a DI container."""
    return DIContainer()

@pytest.fixture
def event_dispatcher():
    """Provide an event dispatcher."""
    return EventDispatcher()