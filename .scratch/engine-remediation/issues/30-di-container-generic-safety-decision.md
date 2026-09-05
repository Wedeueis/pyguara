# Decide whether to harden DIContainer's generic signatures

Type: grilling
Status: open
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

Not yet resolved — HITL grilling ticket, needs the dev's judgment on engineering cost vs.
benefit for a pre-alpha engine.
