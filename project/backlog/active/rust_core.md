---

# RFC-0003: Núcleo Nativo Híbrido em Rust (`pyguara._core_rs`)

* **Status:** Proposto
* **Data:** Outubro de 2026
* **Alvo:** PyGuara v0.4.0+
* **Stack Nativa:** Rust (Edition 2024), `PyO3` (v0.23+), `maturin`, `glam` (SIMD), `rayon` (Data Parallelism), `rustc-hash` (`FxHashMap`)

---

## 1. Contexto e Motivação

A PyGuara atingiu um nível de maturidade arquitetónica de excelência em Python 3.12+ (ECS estrito, DI Container, RenderGraph HDR em ModernGL, física híbrida Pymunk + Swept AABB, e o PyGuara Studio com integração MCP). Contudo, medições internas documentadas no próprio repositório revelam que os *hot loops* numéricos e de agregação sofrem com o teto estrutural da máquina virtual do Python (alocação de objetos no heap, *pointer-chasing*, *refcounting* e retenção do GIL):

1. **Render Batching & Instancing (`ModernGLRenderer` / `Batcher`):** Num lote de 20.000 sprites, o empacotamento vetorizado em NumPy (`instancing.py`) leva ~7.7 ms (de 11.6 ms totais do `render_batch`), enquanto o `Batcher` em Python puro consome ~4x mais (~45 ms) apenas a ordenar comandos e iterar atributos de `Sprite` e `Transform`.


2. **Aritmética Vetorial Fina (`Vector2` / `FlockingSystem`):** Como `Vector2` herda de `pymunk.Vec2d` (uma `NamedTuple` com sobrecarga de inspeção `hasattr`), uma única soma `v1 + v2` custa **452 ns** contra **69 ns** de floats escalares. Isso obrigou a reescrever `flock_force()` inteiramente em variáveis escalares para suportar centenas de agentes.


3. **Sondagem de Física Passo a Passo (`CharacterMover`):** O movimento varrido pixel a pixel (`_move_axis`) invoca `overlap_box()` para cada pixel percorrido, instanciando objetos CFFI `pymunk.Body` e `pymunk.Poly` descartáveis milhares de vezes por segundo.


4. **Algoritmos em Grafos e Grelhas (`ai/pathfinding` e `kits/procgen`):** O cálculo de *Flow Fields* (`dijkstra_map`), `AStarPathfinder` e a propagação de restrições no *Wave Function Collapse* (`generate_wfc`) executam dezenas de milhares de operações em `heapq`, `dict` e `set` do Python com o GIL retido.



### Objetivo

Mover **exclusivamente os motores numéricos, espaciais e de lote** para uma extensão compilada em Rust (`pyguara._core_rs`), mantendo toda a superfície pública, o `EntityManager`, o `DIContainer`, o `EventDispatcher`, os `kits` e o `Studio` em Python puro.

---

## 2. Princípios de Design da Fronteira Python $\leftrightarrow$ Rust

Para evitar que o custo de cruzar a fronteira FFI (Foreign Function Interface) anule os ganhos do Rust, toda implementação em `pyguara._core_rs` deve obedecer a **4 Regras Inegociáveis**:

1. **Regra do Cruzamento Único por Frame (Coarse-Grained FFI):**
* **Proibido:** Fazer um loop `for entity in entities:` em Python que chama uma função Rust 5.000 vezes por frame.
* **Obrigatório:** Cruzar a fronteira **uma única vez por sistema por frame**. O Rust recebe ou mantém a tabela colunar (SoA — *Structure of Arrays*), processa os 10.000 elementos em loop nativo/SIMD e devolve o resultado agregado.


2. **Libertação Sistemática do GIL (`py.allow_threads`):**
* Todo cálculo pesado em Rust (ordenação de batches, integração de partículas/projéteis, *flocking*, *flow fields*, *WFC*) deve operar exclusivamente sobre structs Rust nativas, libertando o GIL via `py.allow_threads(|| { ... })` e permitindo paralelismo real multi-core com `rayon`.


3. **Zero-Copy com Protocolo de Buffer (`PyBuffer` / `memoryview`):**
* Os buffers gerados pelo Rust para a GPU (como o VBO de instâncias de sprites de 15 floats ou o VBO de formas SDF de 11 floats) devem ser expostos ao Python via Buffer Protocol (` &[f32]` $\to$ `memoryview`), permitindo que `self._instance_vbo.write(buffer_view)` no ModernGL envie os dados direto da memória do Rust para o driver OpenGL sem alocação de `bytes` ou `np.ndarray` intermediários.




4. **Fallback Transparente e Paridade de Testes:**
* Cada classe Rust exportada deve ter um ficheiro `.pyi` (Type Stubs) estrito validado pelo `mypy`. A suíte `pytest` atual (incluindo os testes diferenciais de `Rect` e os testes de snapshot visual `.ambr`) deve passar sem alterações.





---

## 3. Estrutura do Repositório e Sistema de Build

A extensão viverá num crate Rust interno gerido pelo **`maturin`** em modo *mixed Python/Rust project*, mantendo o `uv` como gestor principal do ambiente.

```text
pyguara/
├── pyproject.toml             # build-system alterado para maturin
├── Cargo.toml                 # Manifesto do crate pyguara_core_rs
├── rust/                      # Código-fonte Rust (isolado da árvore Python)
│   └── src/
│       ├── lib.rs             # Registo do módulo PyO3 `_core_rs`
│       ├── math.rs            # Vector2, Color, Rect (SIMD / glam)
│       ├── spatial.rs         # SpatialHash, AABB Sweep (CharacterMover)
│       ├── batcher.rs         # RenderQueue + Batcher + Instance Packer
│       ├── pools.rs           # ParticlePool, SparkPool, ProjectilePool
│       ├── flocking.rs        # FlockingSolver (rayon + SpatialHash interno)
│       ├── pathfinding.rs     # GridGraph, AStar, DijkstraMap, FlowField
│       └── procgen.rs         # WFC (Bitset solver), Bridson Poisson, Delaunay
└── pyguara/
    ├── _core_rs.pyi           # Type stubs estritos para mypy / IDE autocomplete
    ├── common/types.py        # Re-exporta Vector2, Rect, Color de _core_rs
    └── ...

```

### Configuração do `pyproject.toml` e `Cargo.toml`

**`pyproject.toml` (secção de build):**

```toml
[build-system]
requires = ["maturin>=1.7,<2.0"]
build-backend = "maturin"

[tool.maturin]
python-source = "."
manifest-path = "Cargo.toml"
module-name = "pyguara._core_rs"
features = ["pyo3/extension-module", "pyo3/abi3-py312"]

```

**`Cargo.toml`:**

```toml
[package]
name = "pyguara_core_rs"
version = "0.4.0"
edition = "2024"

[lib]
name = "_core_rs"
crate-type = ["cdylib"]
path = "rust/src/lib.rs"

[dependencies]
pyo3 = { version = "0.23", features = ["extension-module", "abi3-py312"] }
glam = { version = "0.29", features = ["fast-math"] }
rayon = "1.10"
rustc-hash = "2.1"

[profile.release]
lto = "fat"
codegen-units = 1
opt-level = 3

```

---

## 4. Especificação Detalhada por Subsistema

### Fase 1: Primitivas Matemáticas (`rust/src/math.rs`)

**Problema Atual:** `Vector2` subclasseia `pymunk.Vec2d` (lento em Python e acoplado ao Pymunk); `Color` e `Rect` são dataclasses Python.
**Solução em Rust:**

* Implementar `Vector2` como `#[pyclass(frozen, eq, hash)]` empacotando `glam::Vec2` (8 bytes alinhados, imutável, hashable, compatível com desempacotamento de tuplo `(x, y)` para manter compatibilidade total com o Pymunk CFFI quando passado para `body.position = vec`).


* Implementar todos os métodos existentes em `common/types.py`: `magnitude`, `sqr_magnitude`, `normalize`, `rotated`, `rotate_degrees`, `distance_to`, `lerp`, `clamp_magnitude`, `move_towards`, `reflect`, `reject`, `snapped` e `from_angle_degrees`.


* Implementar `Rect` (`#[pyclass(eq)]` mutável com campos `x, y, width, height: i32`) preservando a aritmética inteira exata validada nos testes diferenciais (`clip`, `clamp`, `fit`, `scale_by`, `inflate`, `contains_point`, `colliderect`, `collidelist`, `collidelistall`).


* Implementar `Color` (`#[pyclass(eq)]` com `r, g, b, a: u8`) com clamping automático em hardware (`saturating_cast`), `lerp`, `multiply`, `darken`, `lighten`, `from_hex` e `to_hsv`/`from_hsv`.



---

### Fase 2: Pipeline de Renderização e Empacotamento GPU (`rust/src/batcher.rs`)

**Problema Atual:** `RenderQueue.sort()`, `Batcher.create_batches()` e `instancing.pack_sprite_instances()` iteram listas de objetos Python, criam tuplos intermediários e convertem listas para arrays NumPy a cada frame.

**Solução em Rust (`NativeRenderBatcher`):**
Em vez de construir milhares de objetos `RenderCommand` em Python e depois copiá-los para `RenderBatch`, o `RenderSystem` delega para uma instância `NativeRenderBatcher` escrita em Rust:

```rust
#[repr(C)]
#[derive(Clone, Copy)]
pub struct GpuSpriteInstance {
    pub pos: [f32; 2],        // 0..2
    pub rot_rad: f32,         // 2
    pub scale: [f32; 2],      // 3..5
    pub size: [f32; 2],       // 5..7
    pub color: [f32; 4],      // 7..11 (normalizado 0.0..1.0)
    pub uv_offset: [f32; 2],  // 11..13
    pub uv_scale: [f32; 2],   // 13..15
} // Exatamente 15 floats (60 bytes) = layout de sprite.vert!

```

1. **Submissão Direta ou em Lote:**
* `NativeRenderBatcher` mantém um `Vec<SpriteCommand>` pré-alocado que nunca encolhe entre frames (`clear()` apenas zera o `len`).
* Cada comando guarda `sort_key: (i32, i32, OrderedFloat<f32>, u32, u32)` correspondente a `(layer, sort_group, depth_or_y, material_id, texture_id)`.




2. **Ordenação e Geração de Spans (`flush_and_pack`):**
* Quando `RenderSystem.flush(camera, viewport)` é chamado, o Python passa `camera.zoom` e `camera.screen_offset(viewport)` para o Rust.


* Com o GIL libertado (`py.allow_threads`), o Rust:
1. Ordena o slice de comandos usando `slice::sort_by_key` (Timsort nativo estável em Rust).


2. Transforma posições de mundo para ecrã (`world * zoom + offset`), converte graus para radianos (`rot.to_radians()`), calcula UVs a partir de `source_rect` e normaliza `RGBA / 255.0`.


3. Escreve diretamente num `Vec<GpuSpriteInstance>` contíguo e gera uma lista compacta de descritores de draw call: `Vec<BatchSpan instance_count material_id, start_instance, texture_id, { }>`.




3. **Consumo Zero-Copy no `ModernGLRenderer`:**
* O `ModernGLRenderer` faz **um único upload de VBO por frame** com `self._instance_vbo.write(batcher.instance_buffer_view())` e executa `vao.render(moderngl.TRIANGLE_STRIP, instances=span.count, first=span.start)` (ou sub-slices do buffer) para cada `BatchSpan`.





---

### Fase 3: Pools de Alta Densidade — Partículas, Sparks e Projéteis (`rust/src/pools.rs`)

**Problema Atual:** `ParticleSystem` (`graphics/components/particles.py`), `Sparks` (`graphics/vfx/sparks.py`) e `ProjectileSystem` (`kits/projectiles/system.py`) iteram milhares de dataclasses em Python a cada frame para integrar Euler (`pos += vel * dt`), amortecimento (`damping`) e interpolação de cor.

**Solução em Rust:**

* Como os três sistemas **já são pools autocontidas (não são entidades ECS)**, a substituição é 100% transparente para os jogos:


* **`NativeParticlePool`:** Armazena partículas em layout SoA (`pos_x`, `pos_y`, `vel_x`, `vel_y`, `acc_x`, `acc_y`, `life`, `life_total`, `rot`, `scale_x`, `scale_y`, `color_start`, `color_end`, `active`).


* `update(dt: f32)` roda em SIMD/Rayon sem GIL e sem tocar em objetos Python.
* `pack_for_render(zoom, offset_x, offset_y)` escreve diretamente um buffer de `GpuSpriteInstance` (15 floats) pronto para o `ModernGLRenderer`!


* **`NativeSparkPool`:** Mesma arquitetura, mas `pack_for_render(offset_x, offset_y)` preenche diretamente o buffer de 11 floats do shader SDF (`shape.vert` / `shape.frag`: `SHAPE_TYPE_CIRCLE` e `SHAPE_TYPE_LINE` para `streak=True`)!


* **`NativeProjectilePool`:** Integra posições em Rust e consulta diretamente o `NativeSpatialHash` em Rust para retornar ao Python **apenas a lista curta de colisões ocorridas neste frame**: `Vec<(ProjectileHitInfo, TargetEntityId)>`, sobre a qual o Python chama `apply_damage()` e dispara o evento `DamageDealt`.





---

### Fase 4: Indexação Espacial, Flocking e Character Mover (`rust/src/spatial.rs` & `flocking.rs`)

#### 4.1. `NativeSpatialHash`

* Substitui o `SpatialHash` em `common/spatial.py` mantendo exatamente a mesma assinatura (`insert`, `remove`, `query_point`, `query_radius`, `query_rect`).


* Internamente usa `FxHashMap<(i32, i32), SmallVec<[u32; 8]>>` e uma tabela densa de `(Vec2, u32 /* mask */)` indexada por um ID inteiro interno mapeado para o `entity_id: str`.


* Elimina todas as alocações de `set` e cálculos de `math.floor` em Python.



#### 4.2. `NativeFlockingSolver` (`ai/flocking_system.py`)

* O `FlockingSystem.update(dt)` em Python extrai os arrays de posições/velocidades/configurações (ou mantém um buffer sincronizado) e chama `solver.step_flock(dt, groups, tick)`.


* O Rust constrói a grelha espacial em paralelo, calcula `flock_force` (coesão + alinhamento + separação + seek) e devolve as novas posições e velocidades. Preserva o modo Gauss-Seidel (sequencial determinístico) por defeito para não quebrar testes existentes, e oferece um flag `parallel=True` (Jacobi via `rayon`) para enxames gigantescos (> 5.000 agentes).



#### 4.3. `CharacterMover` Sem Alocações CFFI (`physics/character_mover.py`)

* **Passo Imediato (sem precisar mudar o Pymunk):** Para Geometria Estática de Níveis (`Tilemap` / `merge_tile_rects`), registar os retângulos sólidos num `StaticSolidGrid` em Rust.


* O `CharacterMover.move()` e `probe()` executam todo o loop de *sweep* pixel a pixel (`while amount != 0`) em Rust contra as AABBs estáticas e os `MovingSolid`s em **menos de 2 microsegundos**, sem fazer uma única chamada CFFI ao Pymunk nem instanciar `pymunk.Body`/`pymunk.Poly`!



---

### Fase 5: Pathfinding e Geração Procedimental (`rust/src/pathfinding.rs` & `procgen.rs`)

Estes módulos têm a **melhor relação custo-benefício de toda a engine** porque a interface com o Python resume-se a passar dimensões/sementes na entrada e receber um dicionário ou lista de coordenadas na saída:

1. **`GridGraph`, `AStarPathfinder`, `dijkstra_map` e `FlowFieldService` (`ai/pathfinding/`):**
* `GridGraph` passa a armazenar paredes num `BitVec` plano (`width * height` bits) e pesos num `Vec<f32>` plano, em vez de `set[ tuple[int, int] ]` e `dict[ tuple[int, int], float ]` em Python.


* `dijkstra_map` e `flow_field` rodam sobre um `BinaryHeap` em Rust com indexação direta $y \times \text{width} + x$ (zero hashing, zero alocação de tuplos). Um *Flow Field* 128x128 passa de ~12 ms em Python para **~0.08 ms em Rust**.




2. **`generate_wfc` (`kits/procgen/wfc.py`):**
* Em vez de `possible: dict[Cell, set[S]]` (que aloca um `set` Python para cada célula da grelha a cada tentativa), o solver em Rust representa os estados possíveis de cada célula como um **`u64` bitmask** (suportando até 64 estados com instruções de CPU `popcnt` / `count_ones()` para entropia e bitwise `&` para propagação!).


* Ganho de velocidade: **50x a 150x mais rápido**.


3. **`delaunay_triangles` e `poisson_disc_sample` (`kits/procgen/`):**
* Portar o algoritmo *hull-fan + split-insert + Lawson flip* (`delaunay.py`) e o amostrador de Bridson (`poisson.py`) diretamente para Rust, consumindo o mesmo estado determinístico do `RandomStream`.





---

## 5. O Que Fica Estritamente em Python (Fronteira de Segurança da DevEx)

Para garantir que programar um jogo na PyGuara continue a ser uma experiência 100% Pythonic e que o **PyGuara Studio** continue a inspecionar tudo em tempo real, **não serão migrados para Rust**:

| Subsistema | Razão Técnica para Permanecer em Python |
| --- | --- |
| **`ecs/` (`Entity`, `BaseComponent`, `EntityManager`)** | Os utilizadores e os `kits` declaram componentes como `@dataclass(slots=True)` com tipos Python arbitrários. Mover o `EntityManager` para Rust forçaria serialização constante ou armazenamento de `PyObject*` opacos, perdendo a introspeção direta do `SceneSerializer` e do `Studio`.

 |
| **`di/` (`DIContainer`, `DIScope`)** | Baseado em `inspect.signature` e `typing.get_type_hints` no registo. Zero impacto na performance de frame.

 |
| **`events/` (`EventDispatcher`)** | Baseado na MRO (`__mro__`) das classes de evento Python e callbacks dinâmicos.

 |
| **`ai/behavior_tree.py` & `fsm.py` & `coroutines.py**` | Executam closures, lambdas e geradores (`yield`) de gameplay escritos em Python. Rodar o orquestrador em Rust exigiria adquirir o GIL a cada nó visitado.

 |
| **`studio/`, `editor/`, `ui/`, `config/`, `persistence/**` | Baseados em reflexão de dataclasses, JSON/MsgPack, Dear ImGui (`imgui_bundle`) e protocolo MCP.

 |

---

## 6. Plano de Rollout Incremental (Sem Quebrar a Engine)

A migração foi desenhada em **4 PRs independentes**, onde a engine continua a compilar e passar em 100% dos testes a cada etapa:

* **Marco 1 (Fundação + Matemática + SpatialHash):**
* Configurar `Cargo.toml` e `maturin` no `pyproject.toml` e no CI (`.github/workflows/ci.yml` e `release.yml`).


* Implementar `Vector2`, `Rect`, `Color` e `SpatialHash` em `rust/src/{math,spatial}.rs`.


* Correr `tests/test_common_types.py`, `tests/test_common_spatial.py` e `tests/performance/test_perf_spatial.py` para validar paridade bit-a-bit e medir o speedup.




* **Marco 2 (Render Batcher + Instance Packer Zero-Copy):**
* Implementar `NativeRenderBatcher` em `rust/src/batcher.rs`.
* Conectar ao `RenderSystem` e `ModernGLRenderer` via `memoryview`.


* Validar com os testes visuais de píxeis (`test_moderngl_pixels.py`, `test_atlas_instancing_pixels.py`, `test_render_pipeline_snapshots.py`) e medir em `test_perf_gl.py`.




* **Marco 3 (Pools de Partículas, Sparks, Projéteis e Flocking):**
* Implementar `rust/src/pools.rs` e `rust/src/flocking.rs`.
* Validar com `test_ai_flocking.py`, `test_perf_flocking.py`, `test_vfx_sparks.py` e `test_kits_projectiles.py`.




* **Marco 4 (Pathfinding, Flow Fields, CharacterMover e Procgen):**
* Implementar `rust/src/pathfinding.rs` e `rust/src/procgen.rs`.
* Validar com `test_pathfinding.py`, `test_flow_field.py`, `test_kits_procgen_*.py` e `test_platformer_feel.py`.





---

## 7. Impacto Esperado (Benchmarks Alvo)

| Operação / Cenário | Hoje (Python 3.12 + NumPy) | Pós-Migração (`_core_rs` Rust) | Ganho Esperado |
| --- | --- | --- | --- |
| **Batching + Packing de 20.000 Sprites** | ~55.0 ms (Batcher + NumPy pack)

 | **~1.2 ms** (Sort + Pack nativo + Zero-copy VBO) | **~45x** |
| **Flocking de 2.000 Agentes (`FlockingSystem`)** | ~18.5 ms (Python escalar)

 | **~0.4 ms** (SIMD `glam` + `rayon`) | **~45x** |
| **Update + Pack de 10.000 Partículas / Projéteis** | ~14.0 ms | **~0.3 ms** (SoA em Rust) | **~45x** |
| **Recompute de Flow Field (Grelha 100x100)** | ~9.5 ms (`heapq` + `dict`)

 | **~0.07 ms** (`Vec` plano + `BinaryHeap`) | **~130x** |
| **Geração WFC (Grelha 40x40, 12 estados)** | ~45.0 ms (`dict` de `set`)

 | **~0.4 ms** (Propagação por bitmask `u64`) | **~110x** |
| **Swept `CharacterMover` (50 atores, 6px/frame)** | ~3.2 ms (300 alocações CFFI Pymunk)

 | **~0.03 ms** (Sweep AABB nativo em Rust) | **~100x** |

Com esta arquitetura, a PyGuara preserva toda a sua identidade — uma engine Python 3.12+ expressiva, testável e nativa para agentes de IA — mas passa a operar com a folga de frame-time de uma engine escrita em Rust/C++.
