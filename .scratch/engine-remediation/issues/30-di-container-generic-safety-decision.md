# Decide whether to harden DIContainer's generic signatures

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: found while executing Drop nominal Protocol inheritance across the 14 sites
(ticket 23)

## Question

[Event dispatcher hot path](11-event-dispatcher-hot-path.md)'s decision assumed that once
nominal Protocol inheritance was dropped, "a genuinely missing method now surfaces — as a
mypy structural-mismatch error wherever the class is used as the protocol type (DI
registration, function parameter, factory return type), or an `AttributeError` at the call
site." Verifying this while executing [Drop nominal Protocol inheritance across the 14
sites](23-drop-nominal-protocol-inheritance.md) found the DI-registration half doesn't
actually hold for this codebase's `DIContainer`.

`register_instance(self, interface: Type[TInterface], instance: TInterface)` and
`register_singleton(self, interface: Type[TInterface], implementation: Type[TImplementation])`
(same shape for `register_transient`/`register_scoped`) use unbounded, and in the
class-registration case entirely *independent*, TypeVars. mypy infers them jointly rather
than checking that the second argument structurally satisfies the first — confirmed with an
isolated repro reproducing the exact pattern: `register(IFoo, Impl())` type-checks cleanly
under `mypy --strict` even when `Impl` is missing a method `IFoo` requires, and even when
passed a completely unrelated type (an `int`). This affects every registration of the 10
(of 13) interfaces here that are **not** `@runtime_checkable`: `IRenderer`, `IWindowBackend`,
`UIRenderer`, `TextureFactory`, `IPhysicsBody`, `IPhysicsEngine`, `IAudioSystem`,
`StorageBackend`, `Graph`, `Heuristic`.

The fallback the decision also named — a missing method raises `AttributeError` at the real
call site instead of silently returning `None` via an inherited stub — is still real and
still a genuine improvement (confirmed directly too). This ticket is only about whether the
*earlier*, DI-registration-time catch is worth engineering for, given it currently isn't
happening.

## To resolve

- Is `Type[TInterface], TInterface` (same TypeVar) even fixable within mypy's inference
  model for a general-purpose auto-wiring container, or does enforcing it require a
  different API shape (e.g. `@overload` per call site, a bound TypeVar per registration
  helper, or dropping the generic convenience entirely for a runtime `isinstance` check
  gated on `@runtime_checkable`)?
- Is `register_singleton`/`register_transient`/`register_scoped`'s independent
  `TInterface`/`TImplementation` pair a bug in its own right (letting
  `register_singleton(IRenderer, SomeUnrelatedClass)` type-check silently), separate from
  the Protocol-inheritance question — worth its own audit finding regardless of what's
  decided here?
- Is a mypy-time catch worth the engineering cost at all, given the runtime `AttributeError`
  fallback already exists and every one of these classes ships with tests exercising its
  real methods? Or is "tests catch it, worst case a clear AttributeError, not mypy" an
  acceptable ongoing posture for a pre-alpha engine?
- If pursued: would making the 10 non-`@runtime_checkable` protocols `@runtime_checkable`
  and adding a runtime `isinstance` assertion inside `register_instance`/`register_singleton`
  (fail fast at registration time, not mypy-time, but still earlier than first real use) be
  an acceptable middle ground?

## Answer

Grilled live with the dev, one sub-question at a time. Researched the mypy mechanics
directly rather than asking, since it's a factual question about the type system, not a
judgment call:

- **Sub-question 1, answered by isolated repro:** the current API shape genuinely cannot
  be hardened at mypy-time. `register_instance(IFoo, MissingMethod())` and
  `register_instance(IFoo, Unrelated())` both type-check clean under `mypy --strict` —
  confirmed the ticket's claim exactly. Root cause: when one unbound TypeVar appears in
  two independent argument positions, mypy solves it by computing the *join* of both
  constraints, which is `object` for two unrelated types, and `object` trivially
  satisfies an unbounded TypeVar. Confirmed by adding `bound=IFoo` to the TypeVar in
  isolation — this *does* produce an error (`object` now violates the bound) — but a
  bound must be a fixed protocol, not "whatever the first argument happened to be," so
  it can't generalize across many protocols in one method. Also tried `@overload` (one
  variant per protocol): this *does* correctly catch the mismatch, but requires
  `di/container.py` to enumerate every protocol in the engine by hand, coupling the
  generic container to every subsystem it currently knows nothing about — rejected on
  that basis alone, not attempted further.
- **Sub-question 2:** not a separate bug — the independent-TypeVar-pair issue in
  `register_singleton`/`transient`/`scoped` is the same root cause as sub-question 1,
  just phrased for the two-argument case. No separate finding needed; whatever's decided
  here applies uniformly.
- **Sub-question 3, the actual decision: do it.** `@runtime_checkable` on the 10
  protocols plus an `isinstance()` assert inside `register_instance()`. Registration
  happens once at bootstrap, not a hot path, so the usual `runtime_checkable` perf
  objection doesn't apply. Turns a possibly-deep, confusing `AttributeError` (wherever
  the missing method first gets called) into a clear failure at the exact bootstrap line
  that registered the wrong thing.
- **Sub-question 4, scoped narrower than the ticket's framing:** the `isinstance()`
  assert lands **only** in `register_instance()`, not `register_singleton`/`transient`/
  `scoped`. Those only have the class (not yet an instance) at registration time, so
  they'd need `issubclass()` instead — which raises `TypeError` for any protocol with
  non-method members (confirmed: 3 of the 10 -- `IRenderer`, `TextureFactory`,
  `IPhysicsBody` -- have `@property` members). A `try/except TypeError` fallback was
  considered and rejected: it would silently no-op exactly on the protocols most likely
  to need it (width/height-style properties are the common shape for renderer/backend
  protocols), creating false confidence rather than real protection. Verified this scope
  covers 100% of current risk anyway: grepped every `register_instance()` call site
  across `bootstrap.py` and all 9 `games/*/bootstrap.py` -- every interface passed is
  either a concrete class (`isinstance()` always works, decorator or not) or already
  `@runtime_checkable` (`IInputBackend`), and none of the 10 protocols are ever
  registered via the class-based methods anywhere in the codebase today.

On mismatch, `register_instance()` raises the existing `DIException` (already used
elsewhere in `container.py`), naming the interface and the instance's actual type.

Lands as one execution ticket — see [Execute the DIContainer runtime safety
check](33-execute-di-container-runtime-safety-check.md).
