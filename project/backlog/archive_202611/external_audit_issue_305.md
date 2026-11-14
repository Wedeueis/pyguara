# **Auditoria Arquitetónica e Registo de Dívida Técnica — PyGuara Engine**

## **1\. Visão Geral e Avaliação da Arquitetura**

| Dimensão | Nota | Resumo Executivo |
| :---- | :---- | :---- |
| **Qualidade de Código & Tipagem** | **9.2 / 10** | Uso exemplar de Python 3.12+ (PEP 695, @runtime\_checkable Protocol, slots=True), docstrings que documentam o *porquê* das decisões arquitetónicas e governação estrita contra dependências circulares (ex.: errors.py no topo). |
| **Arquitetura Core (ECS, DI, Eventos, Loop)** | **9.0 / 10** | Mundos isolados por cena (EntityManager e SystemManager próprios), remoção suave em duas fases, acumulador de passo fixo com interpolação visual (alpha) e separação exemplar entre parentesco espacial (Transform) e posse de ciclo de vida (ChildOf). |
| **Pipeline Gráfico & Física 2D** | **8.5 / 10** | Pipeline ModernGL multi-pass FBO em HDR (f2 / 16-bit float) com instancing vetorizado em NumPy e shaders SDF de primitivas. Física híbrida brilhante: Pymunk para dinâmica/queries e CharacterMover/SolidMover estilo *Celeste* para plataformas/top-down sem penetração. |
| **Ecossistema de Géneros (kits/)** | **9.5 / 10** | Totalmente desacoplado do core. Inclui geração procedimental pura (BSP, WFC, Delaunay sem buracos, Poisson, Placement por vetos), combate por hitboxes/active-frames, progressão, projéteis e direção de hordas. |
| **Coesão de UI e Ferramentas** | **7.5 / 10** | O ponto de maior fragmentação atual: coexistem três camadas sobrepostas (pyguara.ui, pyguara.tools e pyguara.editor/pyguara.studio). |
| **Prontidão para Agentes IA (studio/)** | **9.8 / 10** | A costura única de mutação (EditCommand \-\> CommandStack \-\> Journal) com modos PLAN (diff real por apply+revert) e ASK torna o PyGuara único no mercado para co-criação com agentes (MCP / JSON-lines). |

## **2\. Registo Consolidado de Bugs (Prioridade P0 e P1)**

Estes são defeitos reais identificados na leitura linha a linha do código atual que causam comportamento incorreto, falhas silenciosas ou fugas de memória.

### **P0 — Críticos (Corrigir Imediatamente)**

> 1. **Copy-Paste Acidental em pyguara/graphics/components/\_\_init\_\_.py:**
   * **Ficheiro:** pyguara/graphics/components/\_\_init\_\_.py

   * **Problema:** O ficheiro contém uma cópia integral de pyguara/ui/components/\_\_init\_\_.py (importando Button, Canvas, Checkbox, Widget, etc. de pyguara.ui.components) em vez de exportar os componentes gráficos (Sprite, Camera2D, Animator, AnimationStateMachine, ParticleSystem, Geometry, Box, Circle, FloatingText, ScreenFlash).
   * **Ação:** Substituir pelas exportações corretas do pacote graphics.components.
> 2. **Fuga de VRAM (GPU Memory Leak) ao Descarregar Texturas no ResourceManager:**
   * **Ficheiro:** pyguara/resources/manager.py & pyguara/graphics/backends/moderngl/texture.py

   * **Problema:** Em release(), unload(), unload\_unused() e evict\_to\_budget(), os recursos são removidos com del self.\_cache\[actual\_path\], mas **resource.release() nunca é chamado**. Como GLTexture aloca uma textura na VRAM do OpenGL (moderngl.Texture), remover a referência do dicionário sem chamar gl\_texture.release() deixa a textura órfã na VRAM.
   * **Ação:** Definir um método release(self) \-\> None (no-op por defeito) na classe base Resource (resources/types.py) e invocá-lo num helper central \_evict\_entry(path) usado por todos os métodos de descarga do ResourceManager.
> 3. **Dupla Inversão Vertical e Fuga de Performance em ModernGLRenderer.draw\_text():**
   * **Ficheiro:** pyguara/graphics/backends/moderngl/renderer.py (linhas 488–529) & moderngl/texture.py (linhas 92–95)
   * **Problema:**
     1. draw\_text() chama pygame.image.tobytes(surf, "RGBA", True) (onde True inverte a imagem verticalmente) e passa os bytes para GLTextureFactory.create\_from\_bytes(), que **inverte os bytes uma segunda vez** linha a linha (flipped\_data \= b"".join(...)), anulando a inversão\!
     2. Cada chamada a draw\_text() (ex.: 20 números de dano de FloatingText por frame) cria uma superfície Pygame, aloca uma textura OpenGL nova (ctx.texture), desenha um quad e destrói imediatamente a textura (gl\_texture.release()).
   * **Ação:** Unificar a convenção de orientação em GLTextureFactory e adicionar uma cache LRU simples dict\[tuple\[str, int, tuple\[int, int, int, int\]\], GLTexture\] em ModernGLRenderer para reutilizar texturas de texto entre frames.
> 4. **Vulnerabilidade de Execução Arbitrária de Código via pickle em Saves:**
   * **Ficheiro:** pyguara/persistence/manager.py (linha 273\) & pyguara/persistence/serializer.py (linhas 86, 129, 159\)
   * **Problema:** PersistenceManager.\_decode() lê o formato diretamente do cabeçalho JSON do ficheiro (fmt \= SerializationFormat(meta\_dict.get("format", "json"))) e passa-o para Serializer.deserialize(), que executa pickle.loads(data) se o formato for "binary". Um ficheiro .save modificado externamente pode forçar "format": "binary" com um checksum MD5 válido e executar código arbitrário na máquina do jogador.
   * **Ação:** Remover SerializationFormat.BINARY (pickle) de persistence/serializer.py, mantendo apenas JSON e MSGPACK.
> 5. **Collider.offset Ignorado em Colisores ShapeType.BOX (e no CharacterMover/SolidMover):**
   * **Ficheiro:** pyguara/physics/backends/pymunk\_impl.py (linhas 426–433), character\_mover.py & solid\_mover.py

   * **Problema:** Em PymunkEngine.add\_shape(), ShapeType.CIRCLE passa (offset.x, offset.y) para pymunk.Circle, mas ShapeType.BOX chama pymunk.Poly.create\_box(body, size=(width, height)) sem transform=pymunk.Transform(tx=offset.x, ty=offset.y), ignorando o offset. Da mesma forma, PlatformerSystem, TopDownSystem e SolidMover calculam o centro da caixa apenas a partir de transform.position sem somar collider.offset.
   * **Ação:** Passar pymunk.Transform(tx=offset.x, ty=offset.y) em create\_box e somar collider.offset nas sondagens de CharacterMover/SolidMover.

### **P1 — Altos (Bugs Funcionais e Falhas Silenciosas)**

> 6. **LightSource e AmbientLight Sem Inicialização de BaseComponent (self.entity):**
   * **Ficheiro:** pyguara/graphics/lighting/components.py

   * **Problema:** Ambos usam @dataclass(slots=True) herdando de BaseComponent, mas esqueceram-se de definir def \_\_post\_init\_\_(self): BaseComponent.\_\_init\_\_(self). O slot self.entity fica não inicializado (levantando AttributeError se lido antes de on\_attach).
   * **Ação:** Em vez de repetir \_\_post\_init\_\_ em dezenas de componentes com slots=True, definir \_\_new\_\_ em BaseComponent (instance \= super().\_\_new\_\_(cls); instance.entity \= None; return instance) e apagar todos os \_\_post\_init\_\_ redundantes da codebase.
> 7. **load\_async() Ignora o Orçamento LRU (evict\_to\_budget):**
   * **Ficheiro:** pyguara/resources/manager.py (linhas 273–285 e 449–484)
   * **Problema:** Ao contrário de load(), load\_async() não chama self.\_cache.move\_to\_end(actual\_path) num cache hit, e \_finish() não chama self.evict\_to\_budget(protect=request.key) após inserir o recurso carregado assincronamente na cache.
   * **Ação:** Adicionar move\_to\_end no cache hit de load\_async() e self.evict\_to\_budget(protect=request.key) no final de \_finish().
> 8. **Perda de y\_sort, sort\_offset e sort\_group em WorldPass.submit():**
   * **Ficheiro:** pyguara/graphics/pipeline/passes/world\_pass.py (linhas 79–90)
   * **Problema:** WorldPass.submit() constrói RenderCommand passando z\_index=item.z\_index diretamente sem verificar item.y\_sort (item.position.y \+ item.sort\_offset) e sem copiar sort\_group=item.sort\_group.
   * **Ação:** Alinhar WorldPass.submit() com a lógica de RenderSystem.submit() (ou remover a fila interna de WorldPass, já que Application.\_render\_with\_graph delega o desenho do mundo para SceneManager.render).
> 9. **Desincronização de RandomService e Multi-Comando no Sistema de Replay:**
   * **Ficheiros:** pyguara/application/application.py (linhas 383–404), pyguara/input/manager.py (linhas 253–267) & pyguara/replay/recorder.py

   * **Problema:**
     1. Application.start\_recording() não lê nem fixa a seed atual do RandomService, e Application.load\_replay() não reinicializa o RandomService com data.metadata.seed.
     2. RecordedInputEvent e ReplayRecorder.record\_gamepad\_button/axis não guardam o controller\_id, tornando impossível reproduzir replays de sessões co-op local com múltiplos comandos.
   * **Ação:** Sincronizar RandomService no início da gravação/reprodução e adicionar controller\_id: int | None \= None a RecordedInputEvent.
> 10. **Falsa Prevenção de Fuga de Memória em EventDispatcher (owner=id(owner)):**
    * **Ficheiro:** pyguara/events/dispatcher.py (linhas 40–45, 146–162)
    * **Problema:** HandlerRecord guarda owner=id(owner) para não manter uma referência forte ao dono. Contudo, quando o dono passa um método próprio (dispatcher.subscribe(Evt, self.\_on\_evt, owner=self)), record.callback é um *bound method* que **já retém uma referência forte (\_\_self\_\_) para self**\! Além disso, se um objeto sem método vinculado for destruído sem chamar clear\_subscribers, o Python pode reutilizar o mesmo id() de memória para um novo objeto, causando colisões de ID.
    * **Ação:** Usar weakref.WeakMethod para métodos vinculados (limpando automaticamente registos mortos) ou guardar weakref.ref(owner) em vez de id(owner).
> 11. **Efeitos Secundários Indesejados durante ApprovalMode.PLAN e ASK no Studio:**
    * **Ficheiro:** pyguara/studio/session.py (linhas 296–367)
    * **Problema:** \_plan() e \_queue() aplicam o EditCommand, tiram um snapshot e chamam command.revert(). Isso dispara os callbacks subscribe\_component\_added, removed, changed e subscribe\_entity\_removed no EntityManager duas vezes durante um simples "dry-run".
    * **Ação:** Adicionar um context manager with self.\_world.suppress\_notifications(): em EntityManager para silenciar observadores externos durante o cálculo de diffs de PLAN/ASK.
> 12. **TweenSystem Corre no Passo Fixo sem Ativar Interpolação Visual:**
    * **Ficheiro:** pyguara/scene/base.py (linhas 121–125) & pyguara/animation/tweener.py

    * **Problema:** TweenSystem é registado no SystemManager e corre apenas em fixed\_update (60 Hz). Se tween\_property(entity, "transform.position", ...) for chamado numa entidade sem RigidBody (transform.interpolate \== False), a posição só muda 60 vezes por segundo sem interpolação render\_alpha no Scene.render(), causando *judder* em monitores de 120/144 Hz.
    * **Ação:** Fazer TweenSystem implementar VariableStepSystem (ou ativar transform.interpolate \= True quando um tween controla transform.position).

## **3\. Gargalos de Performance Identificados (Hot Paths)**

> 1. **18.000+ Alocações CFFI/segundo em PymunkEngine.\_probe\_shape() (physics/backends/pymunk\_impl.py):**
   * CharacterMover move entidades 1 pixel de cada vez ao longo de X e Y. Cada passo de 1 pixel chama overlap\_box(), que instancia um novo pymunk.Body(KINEMATIC) e um novo pymunk.Poly.create\_box() no heap CFFI.
   * **Solução:** Manter um \_probe\_body cinemático persistente em PymunkEngine ou usar self.space.bb\_query(pymunk.BB(left, top, right, bottom), shape\_filter) com verificação rápida para formas AABB.
> 2. **Upload de Textura Fullscreen (3.84 MB/frame) na UI OpenGL (graphics/backends/moderngl/ui\_renderer.py):**
   * Sempre que qualquer elemento de UI muda (self.\_dirty \= True), GLUIRenderer.present() inverte na CPU uma pygame.Surface do tamanho do ecrã inteiro (1200x800), converte para bytes e faz upload para a GPU.
   * **Solução:** Como ModernGLRenderer já possui um shader instanciado SDF de retângulos/círculos/linhas (shape.vert/shape.frag) e batching de texturas, fazer o GLUIRenderer desenhar diretamente via instancing GPU \+ cache de texturas de texto, eliminando a superfície Pygame intermediária.
> 3. **Verificação if entity\_id in disabled Por Entidade nas Queries ECS (ecs/manager.py):**
   * Em get\_entities\_with(), get\_entities\_with\_cached() e get\_components(), o filtro de entidades desativadas (self.\_disabled) é testado elemento a elemento dentro do loop Python.
   * **Solução:** Substituir por diferença de conjuntos em C antes do loop:
     Python
     ids \= self.\_matching\_entity\_ids(component\_types, without, any\_of)
     if self.\_disabled:
         ids \= ids \- self.\_disabled

## **4\. Dívida Técnica e Coesão Arquitetónica**

### **4.1. Unificação das Três Camadas de Ferramentas e UI (ui vs tools vs editor/studio)**

Atualmente existem três implementações concorrentes de ferramentas/interfaces:

> 1. **pyguara.ui:** Grafo de cena retido com layout (BoxContainer, GridContainer, ScrollContainer), UIBuilder e o tema **Cerrado**.
> 2. **pyguara.tools:** Ferramentas de debug in-game (HierarchyTool, EntityInspector, ConfigInspector, AssetsTool, TransformGizmo). Desenham retângulos e texto manualmente via UIRenderer com y \+= 16, **não têm scroll** (cortam listas longas), usam cliques na metade esquerda/direita da linha para somar/subtrair 1.0 fixo (NUMBER\_STEP \= 1.0 em tweakable.py) e possuem um TransformGizmo que apenas desenha setas sem suportar drag nem câmara.
> 3. **pyguara.editor \+ pyguara.studio:** A suite de autoria baseada em Dear ImGui (ViewportPanel, TransformGizmo funcional com undo/redo e snap, HistoryPanel, JournalPanel, CommandPalette).

**Plano de Consolidação Recomendado:**

* **Fundir pyguara.editor dentro de pyguara.studio:** O Studio já depende de editor para o contexto ImGui e painéis base (HierarchyPanel, InspectorPanel). Tornar pyguara.studio o único pacote de edição/autoria ImGui.
* **Encolher pyguara.tools:** Remover tools/gizmos.py, tools/hierarchy.py e tools/assets\_browser.py (que duplicam o Studio de forma inferior), mantendo em tools/ apenas overlays leves de runtime (PerformanceMonitor FPS, PhysicsDebugger wireframes e EventMonitor).

### **4.2. Assimetria de Nomenclatura update vs fixed\_update**

* Em Scene, fixed\_update(fixed\_dt) é o passo fixo e update(dt) é o passo variável por frame renderizado.
* Em System (systems/protocols.py), update(dt) é o passo **fixo** e variable\_update(dt) é o passo **variável**.
* Embora documentado no docstring de VariableStepSystem, esta inversão semântica entre Scene e System é uma armadilha constante. Padronizar ou criar um alias explícito antes da versão 1.0 evitará bugs de temporização.

### **4.3. Funcionalidades Incompletas / Stubs no Core**

* **graphics/ninepatch.py:** NinePatchMetrics e NinePatchSprite calculam os 9 retângulos corretamente, mas render\_ninepatch() tem apenas pass. Além disso, UIRenderer.draw\_texture() não aceita source\_rect, impedindo o desenho das 9 fatias sem recortar texturas.
* **scene/transitions.py:** CircularWipeTransition.render() tem um \# TODO e executa apenas um fade normal.
* **ui/types.py:** ShadowScheme.blur está declarado mas documentado como não consumido.
* **ui/components/text\_input.py:** TextInput não possui índice de cursor (edita apenas no fim da string com self.text\[:-1\]), seleção de texto ou suporte a clipboard (Ctrl+C/Ctrl+V).
* **ui/components/text.py:** Label não suporta quebra de linha automática (*word-wrap* / texto multi-linha).
* **tilemap/tiled\_loader.py:** Não suporta tilesets externos (.tsx), camadas comprimidas (base64/zlib) nem camadas de objetos (\<objectgroup\>).
* **ai/navmesh.py:** NavMeshPathfinder usa centróides de polígonos em vez do Funnel Algorithm (*string-pulling*).
* **physics/backends/pymunk\_impl.py:** ShapeType.SEGMENT e ShapeType.POLYGON estão no enum mas não são tratados em add\_shape().

## **5\. Roadmap para Maturidade Comercial / Profissional**

Se o objetivo for posicionar o **PyGuara** como uma opção comercial viável para estúdios independentes (Steam / itch.io), este é o plano de execução por fases:

### **Fase 1: Saneamento e Estabilidade (Curto Prazo)**

> 1. Corrigir os **12 bugs P0/P1** listados na Secção 2 (especialmente o \_\_init\_\_.py de graphics/components, o VRAM leak em ResourceManager, a segurança do Serializer removendo pickle, e o offset de Collider).
> 2. Eliminar a alocação CFFI por pixel em PymunkEngine.\_probe\_shape().
> 3. Adicionar cache de texturas de texto em ModernGLRenderer.draw\_text().

### **Fase 2: Unificação de UI, Texto e Pipeline de Níveis (Médio Prazo)**

> 1. **Unificar editor \+ studio** e limpar ferramentas redundantes em tools/.
> 2. **Completar pyguara.ui:** Adicionar cursor móvel e clipboard em TextInput, *word-wrapping* e marcação básica de Rich Text em Label, e implementar render\_ninepatch().
> 3. **Pipeline de Níveis Completo:** Suportar .tsx externos e \<objectgroup\> no tiled\_loader.py (mapeando objetos do Tiled diretamente para PrefabFactory e TriggerVolume) e adicionar um carregador nativo de **LDtk (.ldtk JSON)**.
> 4. **Parentesco Espacial no SceneSerializer:** Serializar e restaurar o parent de Transform tal como já é feito para ChildOf.

### **Fase 3: Performance Nativa, Áudio Profissional e Distribuição (Longo Prazo)**

> 1. **Aceleração Vetorial / Cython / PyO3 nos Loops Quentes:** Manter a API Python, mas armazenar posições/velocidades de partículas (ParticleSystem, Sparks), projéteis (ProjectileSystem) e boids (FlockingSystem) em buffers NumPy contíguos.
> 2. **Backend de Áudio Moderno (miniaudio / FMOD):** Substituir ou complementar o pygame.mixer com um backend capaz de variação de *pitch* em tempo real (essencial para evitar fadiga auditiva em SFX repetidos), filtros DSP (low-pass filter) e pontos de loop precisos (AudioMeta.loop\_start / loop\_end, que hoje estão declarados em resources/meta.py mas não são suportados pelo pygame.mixer).
> 3. **Pipeline de Build e Exportação Comercial (pyguara/cli/build.py):** Integração com **Nuitka** (compilação para binário nativo sem expor o código-fonte), empacotamento de ativos em arquivo .pak lido pelo ResourceManager e templates de distribuição para Steam (Windows, macOS, SteamOS/Linux).
