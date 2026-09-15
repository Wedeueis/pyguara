/* @ds-bundle: {"format":4,"namespace":"PyguaraDesignSystem_ca79d7","components":[{"name":"Canvas","sourcePath":"components/core/Canvas.jsx"},{"name":"Image","sourcePath":"components/core/Image.jsx"},{"name":"Label","sourcePath":"components/core/Label.jsx"},{"name":"Panel","sourcePath":"components/core/Panel.jsx"},{"name":"ProgressBar","sourcePath":"components/feedback/ProgressBar.jsx"},{"name":"Button","sourcePath":"components/forms/Button.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Slider","sourcePath":"components/forms/Slider.jsx"},{"name":"TextInput","sourcePath":"components/forms/TextInput.jsx"},{"name":"BoxContainer","sourcePath":"components/layout/BoxContainer.jsx"},{"name":"NavBar","sourcePath":"components/navigation/NavBar.jsx"}],"sourceHashes":{"components/core/Canvas.jsx":"4339469822ed","components/core/Image.jsx":"15598fc639fc","components/core/Label.jsx":"dbd8c05d0c3f","components/core/Panel.jsx":"ac6bc8e2a4ee","components/feedback/ProgressBar.jsx":"5dd7002870cf","components/forms/Button.jsx":"9e2f9e43b337","components/forms/Checkbox.jsx":"75ac0962b7a3","components/forms/Slider.jsx":"25547e9094e7","components/forms/TextInput.jsx":"cc82de04bffa","components/layout/BoxContainer.jsx":"cf9c43a30c5d","components/navigation/NavBar.jsx":"e815bfb6c066","ui_kits/docs/DocsPage.jsx":"d4e6389dd905","ui_kits/editor/EditorOverlays.jsx":"a85692c85ec2","ui_kits/editor/EditorPanels.jsx":"4a51a32e1cf2","ui_kits/editor/EditorShell.jsx":"2f655226d7b5","ui_kits/editor/editor-data.js":"e9f25f7490d9","ui_kits/game/GameScreens-standalone.jsx":"8cacc11858a5","ui_kits/game/GameScreens.jsx":"bed2fbabd523","ui_kits/game/doc-page.js":"f52ae9c02fca","ui_kits/site/SitePage.jsx":"e1478122af36","ui_kits/store/StorePage.jsx":"21726f203465"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.PyguaraDesignSystem_ca79d7 = window.PyguaraDesignSystem_ca79d7 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Canvas.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/canvas.py — a cleared drawing surface used
   for mini-maps, previews and graphs. Children do the actual drawing. */
function Canvas({
  width,
  height,
  bgColor,
  grid = false,
  style,
  children,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      position: 'relative',
      width: width ? width + 'px' : '100%',
      height: height ? height + 'px' : '160px',
      background: bgColor || 'var(--surface-inset)',
      border: '1px solid var(--edge)',
      overflow: 'hidden',
      backgroundImage: grid ? 'linear-gradient(to right,var(--edge-subtle) 1px,transparent 1px),linear-gradient(to bottom,var(--edge-subtle) 1px,transparent 1px)' : 'none',
      backgroundSize: grid ? 'var(--size-tile) var(--size-tile)' : 'auto',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Canvas });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Canvas.jsx", error: String((e && e.message) || e) }); }

// components/core/Image.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/image.py — draws a texture into a rect,
   optionally tinted. Pixel art must never be smoothed on upscale. */
function Image({
  src,
  alt = '',
  width,
  height,
  tint,
  pixelated = true,
  style,
  ...rest
}) {
  const img = /*#__PURE__*/React.createElement("img", _extends({
    src: src,
    alt: alt,
    width: width,
    height: height,
    style: {
      display: 'block',
      width: width ? width + 'px' : '100%',
      height: height ? height + 'px' : 'auto',
      imageRendering: pixelated ? 'pixelated' : 'auto',
      ...(tint ? {} : style)
    }
  }, tint ? {} : rest));
  if (!tint) return img;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      position: 'relative',
      display: 'inline-block',
      ...style
    }
  }, rest), img, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      position: 'absolute',
      inset: 0,
      background: tint,
      mixBlendMode: 'multiply',
      pointerEvents: 'none'
    }
  }));
}
Object.assign(__ds_scope, { Image });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Image.jsx", error: String((e && e.message) || e) }); }

// components/core/Label.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/text.py — read-only auto-sizing text.
   Source default font_size is 16 (the engine's size_normal). */
function Label({
  text,
  fontSize = 16,
  color,
  font = 'pixel',
  uppercase = false,
  anchor = 'TOP_LEFT',
  style,
  ...rest
}) {
  const families = {
    pixel: 'var(--font-pixel)',
    display: 'var(--font-display)',
    body: 'var(--font-body)',
    mono: 'var(--font-mono)'
  };
  const align = anchor.includes('CENTER') && !anchor.startsWith('CENTER') ? 'center' : anchor.includes('RIGHT') ? 'right' : 'left';
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'block',
      fontFamily: families[font],
      fontSize: fontSize + 'px',
      lineHeight: 'var(--lh-snug)',
      letterSpacing: font === 'display' ? 'var(--ls-display)' : 'var(--ls-pixel)',
      color: color || 'var(--text-body)',
      textTransform: uppercase ? 'uppercase' : 'none',
      textAlign: align,
      ...style
    }
  }, rest), text);
}
Object.assign(__ds_scope, { Label });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Label.jsx", error: String((e && e.message) || e) }); }

// components/core/Panel.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/panel.py — a colored rectangle with a border.
   Source defaults: color = theme.colors.background, border_width = 1. */
function Panel({
  color,
  borderWidth = 1,
  padding = 'var(--ui-padding)',
  bevel = false,
  as: Tag = 'div',
  style,
  children,
  ...rest
}) {
  const panelStyle = {
    background: color || 'var(--surface-card)',
    border: `${borderWidth}px solid var(--edge-strong)`,
    borderRadius: 'var(--radius-0)',
    padding,
    boxShadow: bevel ? 'var(--shadow-bevel)' : 'none',
    color: 'var(--text-body)',
    fontFamily: 'var(--font-body)',
    ...style
  };
  return /*#__PURE__*/React.createElement(Tag, _extends({
    style: panelStyle
  }, rest), children);
}
Object.assign(__ds_scope, { Panel });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Panel.jsx", error: String((e && e.message) || e) }); }

// components/feedback/ProgressBar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/progress_bar.py. Source: background in
   theme.colors.background, a 1px border, and a left-anchored fill in
   theme.colors.secondary whose width is rect.width * value.
   Value is clamped 0.0-1.0. Default size 200x20. */
function ProgressBar({
  value = 0.5,
  width = 200,
  height = 20,
  fillColor,
  bgColor,
  label,
  style,
  ...rest
}) {
  const v = Math.max(0, Math.min(1, value));
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--ui-gap)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'relative',
      display: 'block',
      width: width + 'px',
      height: height + 'px',
      background: bgColor || 'var(--surface-inset)',
      border: '1px solid var(--edge-strong)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      left: 0,
      top: 0,
      bottom: 0,
      width: v * 100 + '%',
      background: fillColor || 'var(--action-secondary)',
      transition: 'width var(--dur-normal) var(--ease-out-quad)'
    }
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: '12px',
      color: 'var(--text-muted)'
    }
  }, label));
}
Object.assign(__ds_scope, { ProgressBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/ProgressBar.jsx", error: String((e && e.message) || e) }); }

// components/forms/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
/* Mirrors pyguara/ui/components/button.py.
   Source behaviour, exactly: fill = theme.colors.primary; HOVERED and PRESSED
   both fill with theme.colors.secondary; DISABLED fills with
   theme.colors.background; a 2px border is always drawn, switching to
   secondary on FOCUSED; the 16px label is centred. Default size 120x40. */
const SKINS = {
  primary: {
    bg: 'var(--action-primary)',
    hover: 'var(--action-secondary)',
    press: 'var(--action-secondary-press)',
    fg: 'var(--text-on-primary)',
    edge: 'var(--edge-strong)'
  },
  secondary: {
    bg: 'var(--action-secondary)',
    hover: 'var(--action-secondary-hover)',
    press: 'var(--action-secondary-press)',
    fg: 'var(--text-on-secondary)',
    edge: 'var(--edge-strong)'
  },
  wood: {
    bg: 'var(--wood-500)',
    hover: 'var(--wood-400)',
    press: 'var(--wood-700)',
    fg: 'var(--sand-100)',
    edge: 'var(--rock-600)'
  },
  sage: {
    bg: 'var(--colonial-500)',
    hover: 'var(--colonial-400)',
    press: 'var(--colonial-700)',
    fg: 'var(--sage-100)',
    edge: 'var(--colonial-700)'
  },
  ghost: {
    bg: 'transparent',
    hover: 'var(--action-ghost-hover)',
    press: 'var(--theme-press-overlay)',
    fg: 'var(--text-body)',
    edge: 'var(--edge)'
  }
};
const SIZES = {
  small: {
    h: 30,
    px: 10,
    fs: 12
  },
  normal: {
    h: 40,
    px: 16,
    fs: 16
  },
  large: {
    h: 52,
    px: 24,
    fs: 24
  }
};
function Button({
  text,
  children,
  variant = 'primary',
  size = 'normal',
  disabled = false,
  focused = false,
  fullWidth = false,
  bevel = true,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const [press, setPress] = useState(false);
  const s = SKINS[variant] || SKINS.primary;
  const z = SIZES[size] || SIZES.normal;
  const bg = disabled ? 'var(--action-disabled)' : press ? s.press : hover ? s.hover : s.bg;
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    disabled: disabled,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => {
      setHover(false);
      setPress(false);
    },
    onMouseDown: () => setPress(true),
    onMouseUp: () => setPress(false),
    style: {
      minWidth: fullWidth ? '100%' : 'var(--size-button-w)',
      height: z.h + 'px',
      padding: `0 ${z.px}px`,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 'var(--ui-gap)',
      background: bg,
      color: disabled ? 'var(--text-on-disabled)' : s.fg,
      border: `2px solid ${focused ? 'var(--action-secondary)' : s.edge}`,
      borderRadius: 'var(--radius-0)',
      fontFamily: 'var(--font-pixel)',
      fontSize: z.fs + 'px',
      letterSpacing: 'var(--ls-pixel)',
      textTransform: 'uppercase',
      boxShadow: disabled || !bevel ? 'none' : press ? 'var(--shadow-inset-bottom)' : 'var(--shadow-bevel)',
      transform: press && !disabled ? 'translateY(1px)' : 'none',
      cursor: disabled ? 'not-allowed' : 'pointer',
      transition: 'background var(--dur-fast) var(--ease-out-quad)',
      ...style
    }
  }, rest), children || text);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Button.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/checkbox.py. Source geometry is fixed:
   a 20px box, a 10px inner square in theme.colors.secondary when checked,
   5px between box and label, 1px border. Hover lightens the box by 20/channel. */
function Checkbox({
  label,
  checked = false,
  disabled = false,
  onChange,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      fontFamily: 'var(--font-pixel)',
      fontSize: '16px',
      letterSpacing: 'var(--ls-pixel)',
      color: disabled ? 'var(--text-on-disabled)' : 'var(--text-body)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    checked: checked,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.checked),
    style: {
      position: 'absolute',
      opacity: 0,
      width: 0,
      height: 0
    }
  }), /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      width: 'var(--size-checkbox)',
      height: 'var(--size-checkbox)',
      flex: '0 0 auto',
      background: 'var(--surface-inset)',
      border: '1px solid var(--edge-strong)',
      display: 'grid',
      placeItems: 'center'
    }
  }, checked && /*#__PURE__*/React.createElement("span", {
    style: {
      width: '10px',
      height: '10px',
      background: disabled ? 'var(--action-disabled)' : 'var(--action-secondary)',
      display: 'block'
    }
  })), label);
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Slider.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/slider.py. Source: a 2px track line in
   theme.colors.border across the full width, and a radius-8 circular knob in
   theme.colors.secondary that becomes primary while hovered or dragging.
   Default width 150, hit height 20. */
function Slider({
  value = 0,
  min = 0,
  max = 1,
  step = 0,
  width = 150,
  disabled = false,
  showValue = false,
  onChange,
  style,
  ...rest
}) {
  const ratio = max > min ? (value - min) / (max - min) : 0;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--ui-gap)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'relative',
      width: width + 'px',
      height: 'var(--size-slider-h)',
      display: 'block'
    }
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      position: 'absolute',
      left: 0,
      right: 0,
      top: '50%',
      height: '2px',
      marginTop: '-1px',
      background: 'var(--edge-strong)'
    }
  }), /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      position: 'absolute',
      left: `calc(${ratio * 100}% - 8px)`,
      top: '50%',
      marginTop: '-8px',
      width: 'var(--size-slider-knob)',
      height: 'var(--size-slider-knob)',
      borderRadius: 'var(--radius-pill)',
      background: disabled ? 'var(--action-disabled)' : 'var(--action-secondary)',
      border: '1px solid var(--edge-strong)',
      transition: 'background var(--dur-fast) var(--ease-out-quad)'
    }
  }), /*#__PURE__*/React.createElement("input", {
    type: "range",
    value: value,
    min: min,
    max: max,
    step: step || 'any',
    disabled: disabled,
    onChange: e => onChange && onChange(parseFloat(e.target.value)),
    style: {
      position: 'absolute',
      inset: 0,
      width: '100%',
      height: '100%',
      opacity: 0,
      margin: 0,
      cursor: disabled ? 'not-allowed' : 'pointer'
    }
  })), showValue && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: '12px',
      color: 'var(--text-muted)',
      minWidth: '3ch'
    }
  }, typeof value === 'number' ? value.toFixed(2) : value));
}
Object.assign(__ds_scope, { Slider });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Slider.jsx", error: String((e && e.message) || e) }); }

// components/forms/TextInput.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/text_input.py. Source: 200x30 box, 5px text
   padding, 1px border that switches to theme.colors.secondary when active,
   placeholder drawn in theme.colors.border (dim), max_length 32. */
function TextInput({
  value = '',
  placeholder = '',
  width = 200,
  active = false,
  disabled = false,
  maxLength = 32,
  mono = false,
  onChange,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("input", _extends({
    type: "text",
    value: value,
    placeholder: placeholder,
    disabled: disabled,
    maxLength: maxLength,
    onChange: e => onChange && onChange(e.target.value),
    style: {
      width: width + 'px',
      height: 'var(--size-input-h)',
      padding: '0 5px',
      boxSizing: 'border-box',
      background: 'var(--surface-inset)',
      color: disabled ? 'var(--text-on-disabled)' : 'var(--text-body)',
      border: `1px solid ${active ? 'var(--action-secondary)' : 'var(--edge-strong)'}`,
      borderRadius: 'var(--radius-0)',
      fontFamily: mono ? 'var(--font-mono)' : 'var(--font-pixel)',
      fontSize: '16px',
      letterSpacing: mono ? '0' : 'var(--ls-pixel)',
      outline: 'none',
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { TextInput });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/TextInput.jsx", error: String((e && e.message) || e) }); }

// components/layout/BoxContainer.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/layout.py BoxContainer — stacks children linearly.
   Source: direction VERTICAL by default, alignment START, spacing 5.
   Note the engine centres children on the CROSS axis unconditionally. */
function BoxContainer({
  direction = 'VERTICAL',
  align = 'START',
  spacing = 5,
  crossCenter = true,
  style,
  children,
  ...rest
}) {
  const vertical = direction === 'VERTICAL';
  const main = {
    START: 'flex-start',
    CENTER: 'center',
    END: 'flex-end',
    STRETCH: 'space-between'
  }[align] || 'flex-start';
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'flex',
      flexDirection: vertical ? 'column' : 'row',
      justifyContent: main,
      alignItems: crossCenter ? 'center' : 'stretch',
      gap: spacing + 'px',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { BoxContainer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/layout/BoxContainer.jsx", error: String((e && e.message) || e) }); }

// components/navigation/NavBar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Mirrors pyguara/ui/components/navbar.py — a Panel background plus a
   horizontal BoxContainer. Source: height 50, spacing 10, alignment START. */
function NavBar({
  height = 50,
  spacing = 10,
  align = 'START',
  brand,
  children,
  style,
  ...rest
}) {
  const justify = {
    START: 'flex-start',
    CENTER: 'center',
    END: 'flex-end',
    STRETCH: 'space-between'
  }[align] || 'flex-start';
  return /*#__PURE__*/React.createElement("nav", _extends({
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: justify,
      gap: spacing + 'px',
      height: height + 'px',
      padding: '0 var(--space-5)',
      background: 'var(--surface-card)',
      borderBottom: '1px solid var(--edge-strong)',
      fontFamily: 'var(--font-pixel)',
      color: 'var(--text-body)',
      ...style
    }
  }, rest), brand && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--ui-gap)',
      marginRight: 'var(--space-5)'
    }
  }, brand), children);
}
Object.assign(__ds_scope, { NavBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/NavBar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/docs/DocsPage.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  NavBar,
  TextInput,
  Image: DSImage
} = window.PyguaraDesignSystem_ca79d7;
const A = '../../assets/';
/* Sidebar sections are the engine's real top-level packages. */
const NAV = [['Getting started', ['Install', 'Your first scene', 'Project layout']], ['ecs', ['EntityManager', 'Component', 'Query cache', 'Events']], ['graphics', ['Render pipeline', 'Spritesheet & Atlas', 'Animation system', 'Nine-patch', 'Lighting', 'VFX']], ['physics', ['PhysicsSystem', 'Collider & RigidBody', 'PlatformerController', 'Trigger volumes', 'Joints']], ['ui', ['UITheme', 'Theme presets', 'Components', 'Layout', 'Constraints']], ['ai', ['Behavior tree', 'FSM', 'Steering', 'Pathfinding', 'Navmesh']], ['resources', ['ResourceManager', 'Loaders', 'Meta files', 'Hot reload']], ['scene', ['SceneManager', 'Serializer', 'Transitions']], ['tools', ['Editor', 'Performance', 'Event monitor', 'Gizmos', 'Debugger']]];
function DocsApp() {
  const [active, setActive] = React.useState('Theme presets');
  const [q, setQ] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100vh',
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr)'
    }
  }, /*#__PURE__*/React.createElement(NavBar, {
    height: 58,
    align: "STRETCH",
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 30,
      padding: '0 22px',
      borderBottom: '1px solid var(--edge-strong)'
    },
    brand: /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 10
      }
    }, /*#__PURE__*/React.createElement("img", {
      src: A + 'art/badge-pyguara-mark.png',
      alt: "Pyguara Engine",
      style: {
        height: 34
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--text-faint)',
        border: '1px solid var(--edge)',
        padding: '2px 6px'
      }
    }, "0.9.0-dev"))
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(TextInput, {
    value: q,
    onChange: setQ,
    placeholder: "Search docs",
    mono: true,
    width: 200,
    style: {
      height: 28,
      fontSize: 12
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "GitHub",
    variant: "ghost",
    size: "small"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,232px) minmax(0,1fr)',
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("aside", {
    style: {
      position: 'sticky',
      top: 58,
      alignSelf: 'start',
      maxHeight: 'calc(100vh - 58px)',
      overflow: 'auto',
      borderRight: '1px solid var(--edge)',
      padding: '22px 14px',
      background: 'var(--surface-card)'
    }
  }, NAV.map(([sec, items]) => /*#__PURE__*/React.createElement("div", {
    key: sec,
    style: {
      marginBottom: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      letterSpacing: 'var(--ls-caps)',
      textTransform: 'uppercase',
      color: 'var(--action-secondary)',
      marginBottom: 7
    }
  }, sec), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, items.map(it => /*#__PURE__*/React.createElement("button", {
    key: it,
    type: "button",
    onClick: () => setActive(it),
    style: {
      textAlign: 'left',
      padding: '4px 8px',
      border: 0,
      borderLeft: '2px solid ' + (active === it ? 'var(--action-primary)' : 'transparent'),
      background: active === it ? 'var(--action-ghost-hover)' : 'transparent',
      color: active === it ? 'var(--text-heading)' : 'var(--text-muted)',
      fontFamily: 'var(--font-body)',
      fontSize: 14,
      cursor: 'pointer'
    }
  }, it)))))), /*#__PURE__*/React.createElement("main", {
    style: {
      padding: '40px 32px 80px',
      maxWidth: 820,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginBottom: 12
    }
  }, "ui / ", active), /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontFamily: 'var(--font-pixel)',
      fontSize: 30,
      letterSpacing: 'var(--ls-pixel)',
      color: 'var(--text-heading)'
    }
  }, "Theme presets"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 18,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-muted)',
      maxWidth: '66ch',
      textWrap: 'pretty'
    }
  }, /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 15
    }
  }, "pyguara.ui.theme_presets"), " ships six ready-to-use themes. All are immutable \u2014 clone one and modify the copy."), /*#__PURE__*/React.createElement(Panel, {
    padding: "0",
    style: {
      marginTop: 26,
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '7px 12px',
      borderBottom: '1px solid var(--edge)',
      background: 'var(--surface-raised)',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      display: 'flex',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("span", null, "python"), /*#__PURE__*/React.createElement("span", null, "theme_presets.py")), /*#__PURE__*/React.createElement("pre", {
    style: {
      margin: 0,
      padding: '14px 16px',
      overflow: 'auto',
      fontFamily: 'var(--font-mono)',
      fontSize: 14,
      lineHeight: 1.65,
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-cool)'
    }
  }, "from"), " pyguara.ui.theme_presets ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-cool)'
    }
  }, "import"), " Themes", '\n', /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-cool)'
    }
  }, "from"), " pyguara.ui.theme ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-cool)'
    }
  }, "import"), " set_theme", '\n\n', /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)'
    }
  }, "# Use dark theme"), '\n', "set_theme(Themes.DARK)", '\n\n', /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)'
    }
  }, "# Customize a preset"), '\n', "my_theme = Themes.LIGHT.clone()", '\n', "my_theme.colors.primary = Color(", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--state-warn)'
    }
  }, "255"), ", ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--state-warn)'
    }
  }, "0"), ", ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--state-warn)'
    }
  }, "0"), ")", '\n', "set_theme(my_theme)")), /*#__PURE__*/React.createElement("h2", {
    style: {
      marginTop: 38,
      fontFamily: 'var(--font-pixel)',
      fontSize: 20,
      letterSpacing: 'var(--ls-pixel)',
      color: 'var(--text-heading)'
    }
  }, "Available presets"), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: 'auto',
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      minWidth: 520,
      borderCollapse: 'collapse',
      fontSize: 14
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, ['Name', 'primary', 'background', 'border width', 'radius'].map(h => /*#__PURE__*/React.createElement("th", {
    key: h,
    style: {
      textAlign: 'left',
      padding: '8px 10px',
      borderBottom: '2px solid var(--edge-strong)',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      letterSpacing: 'var(--ls-caps)',
      textTransform: 'uppercase',
      color: 'var(--text-faint)',
      fontWeight: 400
    }
  }, h)))), /*#__PURE__*/React.createElement("tbody", null, [['DARK', '70, 130, 180', '32, 32, 32', '2', '0'], ['LIGHT', '41, 128, 185', '236, 240, 241', '1', '4'], ['HIGH_CONTRAST', '255, 255, 255', '0, 0, 0', '3', '0'], ['CYBERPUNK', '255, 0, 255', '10, 10, 20', '2', '0'], ['FOREST', '46, 125, 50', '33, 43, 33', '2', '8'], ['RETRO', '255, 152, 0', '66, 66, 66', '3', '0']].map(r => /*#__PURE__*/React.createElement("tr", {
    key: r[0]
  }, r.map((c, i) => /*#__PURE__*/React.createElement("td", {
    key: i,
    style: {
      padding: '8px 10px',
      borderBottom: '1px solid var(--edge-subtle)',
      fontFamily: i ? 'var(--font-mono)' : 'var(--font-pixel)',
      fontSize: i ? 13 : 12,
      color: i ? 'var(--text-muted)' : 'var(--text-body)'
    }
  }, c))))))), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "14px 16px",
    style: {
      marginTop: 30,
      background: 'var(--surface-inset)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      letterSpacing: 'var(--ls-caps)',
      textTransform: 'uppercase',
      color: 'var(--action-secondary)'
    }
  }, "Note"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '7px 0 0',
      fontSize: 15,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-muted)'
    }
  }, "Themes serialize to JSON with ", /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: 'var(--font-mono)'
    }
  }, "UITheme.to_json()"), " and load with", /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: 'var(--font-mono)'
    }
  }, " UITheme.load(path)"), ", so a game can ship themes as resources.")), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 14,
      marginTop: 40,
      paddingTop: 20,
      borderTop: '1px solid var(--edge)'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "\u2190 UITheme",
    variant: "ghost",
    size: "small"
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Components \u2192",
    variant: "ghost",
    size: "small"
  })))));
}
Object.assign(window, {
  DocsApp
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/docs/DocsPage.jsx", error: String((e && e.message) || e) }); }

// ui_kits/editor/EditorOverlays.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  Checkbox,
  ProgressBar
} = window.PyguaraDesignSystem_ca79d7;

/* pyguara/tools/performance.py — a 150x60 rect at (10,10), black fill,
   2px green border, "FPS: n" at 20px; the text turns red below 30 fps. */
function PerformanceMonitor({
  fps = 60
}) {
  const c = fps < 30 ? 'var(--dbg-fps-bad)' : 'var(--dbg-fps-ok)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: 10,
      top: 10,
      width: 150,
      height: 60,
      background: '#000',
      border: '2px solid ' + c,
      padding: '10px',
      boxSizing: 'border-box',
      zIndex: 15
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-pixel)',
      fontSize: 20,
      color: c,
      letterSpacing: 'var(--ls-pixel)'
    }
  }, "FPS: ", fps));
}

/* pyguara/tools/shortcuts_panel.py — 400x300 centred, rgba(10,10,20,240) fill,
   2px white border, yellow 24px heading, green keys, white descriptions. */
function ShortcutsPanel({
  onClose
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '50%',
      top: '50%',
      transform: 'translate(-50%,-50%)',
      width: 400,
      background: 'rgba(10,10,20,.941)',
      border: '2px solid #fff',
      padding: '30px 40px',
      boxSizing: 'border-box',
      zIndex: 30
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-pixel)',
      fontSize: 20,
      color: '#ff0',
      letterSpacing: 'var(--ls-pixel)'
    }
  }, "Developer Tools"), /*#__PURE__*/React.createElement("table", {
    style: {
      marginTop: 16,
      borderCollapse: 'collapse',
      fontFamily: 'var(--font-pixel)',
      fontSize: 13
    }
  }, /*#__PURE__*/React.createElement("tbody", null, window.EditorData.shortcuts.map(([k, d]) => /*#__PURE__*/React.createElement("tr", {
    key: k
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      color: '#64ff64',
      padding: '3px 26px 3px 0'
    }
  }, k), /*#__PURE__*/React.createElement("td", {
    style: {
      color: '#fff'
    }
  }, d))))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onClose,
    style: {
      marginTop: 18,
      background: 'none',
      border: 0,
      padding: 0,
      color: '#969696',
      fontFamily: 'var(--font-pixel)',
      fontSize: 11,
      cursor: 'pointer'
    }
  }, "Press F8 to Close"));
}

/* pyguara/tools/event_monitor.py — the engine is event-driven; this is the bus tap. */
function EventMonitor({
  onClose
}) {
  return /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "0",
    style: {
      position: 'absolute',
      left: 10,
      bottom: 10,
      width: 360,
      zIndex: 16,
      boxShadow: 'var(--shadow-stamp)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...window.panelTitle
    }
  }, /*#__PURE__*/React.createElement("span", null, "Event Monitor"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onClose,
    style: {
      background: 'none',
      border: 0,
      color: 'var(--text-muted)',
      cursor: 'pointer',
      fontFamily: 'var(--font-mono)',
      fontSize: 13
    }
  }, "\xD7")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '6px 8px',
      maxHeight: 150,
      overflow: 'auto',
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, window.EditorData.events.map(([t, n, d], i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'grid',
      gridTemplateColumns: '46px 1fr',
      gap: 6,
      fontFamily: 'var(--font-mono)',
      fontSize: 11
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)'
    }
  }, t), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-cool)'
    }
  }, n), " ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, d))))));
}
function PhysicsLegend() {
  const items = [['var(--dbg-collider-active)', 'collider active'], ['var(--dbg-collider-sleeping)', 'sleeping'], ['var(--dbg-collider-contact)', 'contact'], ['var(--dbg-raycast)', 'raycast'], ['var(--dbg-pathfinding)', 'pathfinding']];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      right: 10,
      top: 10,
      background: 'rgba(0,0,0,.72)',
      border: '1px solid var(--edge)',
      padding: '7px 9px',
      zIndex: 15,
      display: 'flex',
      flexDirection: 'column',
      gap: 3
    }
  }, items.map(([c, l]) => /*#__PURE__*/React.createElement("div", {
    key: l,
    style: {
      display: 'flex',
      gap: 6,
      alignItems: 'center',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: '#fff'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 12,
      height: 8,
      background: c,
      display: 'block',
      outline: '1px solid rgba(255,255,255,.25)'
    }
  }), l)));
}
Object.assign(window, {
  PerformanceMonitor,
  ShortcutsPanel,
  EventMonitor,
  PhysicsLegend
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/editor/EditorOverlays.jsx", error: String((e && e.message) || e) }); }

// ui_kits/editor/EditorPanels.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  Checkbox,
  Slider,
  TextInput,
  Canvas: DSCanvas,
  ProgressBar
} = window.PyguaraDesignSystem_ca79d7;
const panelChrome = {
  background: 'var(--surface-card)',
  border: '1px solid var(--edge-strong)',
  display: 'flex',
  flexDirection: 'column',
  minHeight: 0
};
const panelTitle = {
  height: 26,
  flex: '0 0 auto',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0 8px',
  background: 'var(--surface-raised)',
  borderBottom: '1px solid var(--edge)',
  fontFamily: 'var(--font-pixel)',
  fontSize: 12,
  letterSpacing: 'var(--ls-pixel)',
  color: 'var(--text-heading)'
};
const panelBody = {
  flex: 1,
  overflow: 'auto',
  padding: 8,
  minHeight: 0
};
function EditorPanel({
  title,
  actions,
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      ...panelChrome,
      ...style
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: panelTitle
  }, /*#__PURE__*/React.createElement("span", null, title), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      gap: 6
    }
  }, actions)), /*#__PURE__*/React.createElement("div", {
    style: panelBody
  }, children));
}

/* pyguara/editor/panels/hierarchy.py — label is "tag.name (id[:8])", or just id[:8] with no Tag. */
function HierarchyPanel({
  entities,
  selected,
  onSelect,
  filter,
  onFilter
}) {
  const list = entities.filter(e => !filter || (e.tag || e.id).toLowerCase().includes(filter.toLowerCase()));
  return /*#__PURE__*/React.createElement(EditorPanel, {
    title: "Hierarchy",
    style: {
      gridArea: 'left'
    },
    actions: /*#__PURE__*/React.createElement(Button, {
      text: "+",
      variant: "ghost",
      size: "small",
      style: {
        minWidth: 24,
        height: 20,
        padding: 0,
        fontSize: 12
      }
    })
  }, /*#__PURE__*/React.createElement(TextInput, {
    value: filter,
    onChange: onFilter,
    placeholder: "filter",
    width: 0,
    mono: true,
    style: {
      width: '100%',
      height: 24,
      fontSize: 12,
      marginBottom: 8
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 1
    }
  }, list.map(e => {
    const on = selected === e.id;
    return /*#__PURE__*/React.createElement("button", {
      key: e.id,
      type: "button",
      onClick: () => onSelect(e.id),
      style: {
        textAlign: 'left',
        padding: '5px 7px',
        border: '1px solid ' + (on ? 'var(--action-secondary)' : 'transparent'),
        background: on ? 'var(--theme-hover-overlay)' : 'transparent',
        color: on ? 'var(--text-heading)' : 'var(--text-body)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        cursor: 'pointer',
        display: 'flex',
        gap: 6,
        alignItems: 'baseline'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: on ? 'var(--action-secondary)' : 'var(--text-faint)'
      }
    }, e.tag ? '\u25aa' : '\u25ab'), /*#__PURE__*/React.createElement("span", null, e.tag ? e.tag : '(untagged)'), /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text-faint)',
        fontSize: 11
      }
    }, "(", e.id, ")"));
  }), !list.length && /*#__PURE__*/React.createElement(Label, {
    text: "No entities match.",
    fontSize: 12,
    color: "var(--text-faint)"
  })));
}

/* pyguara/editor/panels/inspector.py — Entity ID, ResourceLink source + save button,
   separator, then one collapsing header per component drawn by InspectorDrawer. */
function InspectorPanel({
  entity
}) {
  const [open, setOpen] = React.useState({});
  if (!entity) return /*#__PURE__*/React.createElement(EditorPanel, {
    title: "Inspector",
    style: {
      gridArea: 'right'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "No entity selected.",
    fontSize: 12,
    color: "var(--text-faint)"
  }));
  const names = Object.keys(entity.comps);
  return /*#__PURE__*/React.createElement(EditorPanel, {
    title: "Inspector",
    style: {
      gridArea: 'right'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, "Entity ID: ", entity.id), entity.src && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      wordBreak: 'break-all'
    }
  }, "Source: ", entity.src), /*#__PURE__*/React.createElement(Button, {
    text: "Save to Source Asset",
    variant: "secondary",
    size: "small",
    style: {
      marginTop: 6,
      width: '100%',
      fontSize: 11
    }
  })), /*#__PURE__*/React.createElement("hr", {
    style: {
      border: 0,
      borderTop: '1px solid var(--edge)',
      margin: '10px 0'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, names.map(n => {
    const isOpen = open[n] !== false;
    return /*#__PURE__*/React.createElement("div", {
      key: n,
      style: {
        border: '1px solid var(--edge-subtle)'
      }
    }, /*#__PURE__*/React.createElement("button", {
      type: "button",
      onClick: () => setOpen(o => ({
        ...o,
        [n]: !isOpen
      })),
      style: {
        width: '100%',
        textAlign: 'left',
        display: 'flex',
        gap: 6,
        alignItems: 'center',
        padding: '6px 8px',
        background: 'var(--surface-raised)',
        border: 0,
        color: 'var(--text-heading)',
        fontFamily: 'var(--font-pixel)',
        fontSize: 12,
        letterSpacing: 'var(--ls-pixel)',
        cursor: 'pointer'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--action-secondary)',
        width: 8
      }
    }, isOpen ? '\u25be' : '\u25b8'), n), isOpen && /*#__PURE__*/React.createElement("div", {
      style: {
        padding: '7px 8px',
        display: 'flex',
        flexDirection: 'column',
        gap: 5
      }
    }, Object.entries(entity.comps[n]).map(([k, v]) => /*#__PURE__*/React.createElement(FieldRow, {
      key: k,
      name: k,
      value: v
    }))));
  })));
}

/* InspectorDrawer maps field types to imgui widgets: bool -> checkbox,
   float -> drag_float, int -> drag_int, str -> input_text. */
function FieldRow({
  name,
  value
}) {
  const isBool = value === 'True' || value === 'False';
  const isNum = /^\(?-?[0-9]/.test(value);
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'grid',
      gridTemplateColumns: '82px 1fr',
      gap: 6,
      alignItems: 'center',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, name), isBool ? /*#__PURE__*/React.createElement(Checkbox, {
    label: "",
    checked: value === 'True',
    style: {
      fontSize: 11
    }
  }) : /*#__PURE__*/React.createElement("span", {
    style: {
      background: 'var(--surface-inset)',
      border: '1px solid var(--edge)',
      padding: '3px 6px',
      color: isNum ? 'var(--text-numeric)' : 'var(--text-body)',
      fontSize: 11,
      cursor: isNum ? 'ew-resize' : 'text',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, value));
}

/* pyguara/editor/panels/assets.py — Registry list, separator, Cache (Loaded) list,
   plus a separate Resource Inspector window for the selection. */
function AssetsPanel({
  selected,
  onSelect
}) {
  const D = window.EditorData;
  const [openReg, setOpenReg] = React.useState(true);
  const [openCache, setOpenCache] = React.useState(true);
  const Head = ({
    label,
    open,
    set
  }) => /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => set(!open),
    style: {
      display: 'flex',
      gap: 6,
      alignItems: 'center',
      background: 'none',
      border: 0,
      padding: '2px 0',
      color: 'var(--text-heading)',
      fontFamily: 'var(--font-pixel)',
      fontSize: 11,
      letterSpacing: 'var(--ls-pixel)',
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--action-secondary)'
    }
  }, open ? '\u25be' : '\u25b8'), label);
  const Item = ({
    label,
    active,
    onClick
  }) => /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onClick,
    style: {
      textAlign: 'left',
      padding: '3px 6px',
      border: 0,
      background: active ? 'var(--theme-hover-overlay)' : 'transparent',
      color: active ? 'var(--action-secondary)' : 'var(--text-muted)',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      cursor: 'pointer',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, label);
  return /*#__PURE__*/React.createElement(EditorPanel, {
    title: "Assets",
    style: {
      gridArea: 'assets'
    }
  }, /*#__PURE__*/React.createElement(Head, {
    label: "Registry",
    open: openReg,
    set: setOpenReg
  }), openReg && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      marginBottom: 8
    }
  }, D.registry.map(r => /*#__PURE__*/React.createElement(Item, {
    key: r,
    label: r
  }))), /*#__PURE__*/React.createElement("hr", {
    style: {
      border: 0,
      borderTop: '1px solid var(--edge)',
      margin: '6px 0'
    }
  }), /*#__PURE__*/React.createElement(Head, {
    label: "Cache (Loaded)",
    open: openCache,
    set: setOpenCache
  }), openCache && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, D.cache.map(([t, n, p]) => /*#__PURE__*/React.createElement(Item, {
    key: p,
    label: '[' + t + '] ' + n,
    active: selected === p,
    onClick: () => onSelect(p)
  }))));
}
function ResourceInspector({
  path,
  onClose
}) {
  if (!path) return null;
  const D = window.EditorData;
  const row = D.cache.find(c => c[2] === path);
  const isData = row && row[0] === 'DataResource';
  return /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "0",
    style: {
      position: 'absolute',
      right: 16,
      bottom: 16,
      width: 320,
      zIndex: 20,
      boxShadow: 'var(--shadow-stamp-lg)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: panelTitle
  }, /*#__PURE__*/React.createElement("span", null, "Resource Inspector"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onClose,
    style: {
      background: 'none',
      border: 0,
      color: 'var(--text-muted)',
      cursor: 'pointer',
      fontFamily: 'var(--font-mono)',
      fontSize: 13
    }
  }, "\xD7")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-muted)',
      wordBreak: 'break-all'
    }
  }, "Path: ", path), isData ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6,
      margin: '10px 0'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Save to Disk",
    size: "small",
    variant: "secondary",
    style: {
      fontSize: 11
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Spawn into Scene",
    size: "small",
    style: {
      fontSize: 11
    }
  })), /*#__PURE__*/React.createElement("hr", {
    style: {
      border: 0,
      borderTop: '1px solid var(--edge)',
      margin: '8px 0'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 5
    }
  }, /*#__PURE__*/React.createElement(FieldRow, {
    name: "Tag.name",
    value: "guara_player"
  }), /*#__PURE__*/React.createElement(FieldRow, {
    name: "Transform",
    value: "(320.0, 448.0)"
  }), /*#__PURE__*/React.createElement(FieldRow, {
    name: "RigidBody.mass",
    value: "12.0"
  }), /*#__PURE__*/React.createElement(FieldRow, {
    name: "Collider.is_sensor",
    value: "False"
  }))) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-muted)',
      marginTop: 8
    }
  }, "Type: ", row ? row[0] : 'Resource'), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginTop: 4
    }
  }, "Manual editing not supported for this type.")), /*#__PURE__*/React.createElement(Button, {
    text: "Close",
    size: "small",
    variant: "ghost",
    onClick: onClose,
    style: {
      marginTop: 10,
      fontSize: 11
    }
  })));
}
Object.assign(window, {
  EditorPanel,
  HierarchyPanel,
  InspectorPanel,
  AssetsPanel,
  ResourceInspector,
  FieldRow,
  panelTitle
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/editor/EditorPanels.jsx", error: String((e && e.message) || e) }); }

// ui_kits/editor/EditorShell.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  Checkbox,
  Slider,
  Canvas: DSCanvas,
  NavBar,
  Image: DSImage,
  ProgressBar
} = window.PyguaraDesignSystem_ca79d7;
function MenuBar({
  theme,
  onTheme,
  menu,
  onMenu,
  tools,
  toggleTool
}) {
  const items = {
    File: [['Save Scene', 'Ctrl+S'], ['Load Scene', 'Ctrl+L']],
    View: [['Hierarchy', null], ['Inspector', null], ['Assets', null]],
    Tools: window.EditorData.shortcuts.map(([k, d]) => [d, k])
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      zIndex: 40
    }
  }, /*#__PURE__*/React.createElement(NavBar, {
    height: 34,
    spacing: 2,
    align: "STRETCH",
    style: {
      padding: '0 10px'
    },
    brand: /*#__PURE__*/React.createElement(DSImage, {
      src: "../../assets/art/badge-pyguara-mark.png",
      height: 24,
      alt: "Pyguara Engine"
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 2,
      alignItems: 'center',
      marginRight: 'auto'
    }
  }, Object.keys(items).map(m => /*#__PURE__*/React.createElement("button", {
    key: m,
    type: "button",
    onClick: () => onMenu(menu === m ? null : m),
    style: {
      background: menu === m ? 'var(--theme-hover-overlay)' : 'transparent',
      border: 0,
      padding: '5px 9px',
      color: 'var(--text-body)',
      fontFamily: 'var(--font-pixel)',
      fontSize: 12,
      letterSpacing: 'var(--ls-pixel)',
      cursor: 'pointer'
    }
  }, m))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)'
    }
  }, "scene_roca_01"), /*#__PURE__*/React.createElement(Button, {
    text: theme === 'light' ? 'Dusk' : 'Day',
    variant: "ghost",
    size: "small",
    onClick: onTheme,
    style: {
      fontSize: 11,
      minWidth: 56
    }
  }))), menu && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 34,
      left: menu === 'File' ? 44 : menu === 'View' ? 86 : 132,
      background: 'var(--surface-raised)',
      border: '1px solid var(--edge-strong)',
      boxShadow: 'var(--shadow-stamp)',
      minWidth: 210,
      padding: 4
    }
  }, items[menu].map(([label, hint]) => {
    const isTool = menu === 'Tools';
    const on = isTool && tools[label];
    return /*#__PURE__*/React.createElement("button", {
      key: label,
      type: "button",
      onClick: () => {
        isTool && toggleTool(label);
        onMenu(null);
      },
      style: {
        width: '100%',
        display: 'flex',
        justifyContent: 'space-between',
        gap: 16,
        padding: '6px 8px',
        background: 'none',
        border: 0,
        color: 'var(--text-body)',
        fontFamily: 'var(--font-pixel)',
        fontSize: 12,
        cursor: 'pointer',
        textAlign: 'left'
      }
    }, /*#__PURE__*/React.createElement("span", null, isTool ? (on ? '\u2713 ' : '\u00a0\u00a0\u00a0') + label : label), hint && /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text-faint)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11
      }
    }, hint));
  })));
}
function Viewport({
  tools,
  gizmos,
  onGizmos,
  zoom,
  onZoom
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      gridArea: 'view',
      position: 'relative',
      background: 'var(--surface-inset)',
      border: '1px solid var(--edge-strong)',
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      ...window.panelTitle
    }
  }, /*#__PURE__*/React.createElement("span", null, "Scene \u2014 roca_01"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      gap: 12,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: "Gizmos",
    checked: gizmos,
    onChange: onGizmos,
    style: {
      fontSize: 11
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      gap: 6,
      alignItems: 'center',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)'
    }
  }, "zoom", /*#__PURE__*/React.createElement(Slider, {
    value: zoom,
    min: 1,
    max: 4,
    step: 0.5,
    width: 70,
    onChange: onZoom
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      minWidth: 26
    }
  }, zoom.toFixed(1), "\xD7")))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      position: 'relative',
      overflow: 'hidden',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/art/scene-window-grove.png",
    alt: "Cerrado scene",
    style: {
      position: 'absolute',
      inset: 0,
      width: '100%',
      height: '100%',
      objectFit: 'cover'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      backgroundImage: 'linear-gradient(to right,rgba(0,0,0,.14) 1px,transparent 1px),linear-gradient(to bottom,rgba(0,0,0,.14) 1px,transparent 1px)',
      backgroundSize: '32px 32px'
    }
  }), gizmos && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '26%',
      top: '46%',
      width: 56,
      height: 80,
      border: '2px solid rgba(0,255,0,.588)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: -16,
      left: 0,
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: '#0f0'
    }
  }, "guara_player")), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '54%',
      top: '62%',
      width: 128,
      height: 32,
      border: '2px solid rgba(128,128,128,.588)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '72%',
      top: '58%',
      width: 40,
      height: 40,
      border: '2px solid rgba(255,0,0,.706)',
      borderRadius: '50%'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '30%',
      top: '52%',
      width: 180,
      height: 2,
      background: 'var(--dbg-raycast)',
      transformOrigin: 'left',
      transform: 'rotate(-9deg)'
    }
  })), tools['Performance Monitor'] && /*#__PURE__*/React.createElement(window.PerformanceMonitor, {
    fps: 60
  }), tools['Physics Debugger'] && /*#__PURE__*/React.createElement(window.PhysicsLegend, null), tools['Event Monitor'] && /*#__PURE__*/React.createElement(window.EventMonitor, {
    onClose: () => {}
  })), /*#__PURE__*/React.createElement("footer", {
    style: {
      flex: '0 0 auto',
      height: 24,
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '0 8px',
      borderTop: '1px solid var(--edge)',
      background: 'var(--surface-card)',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "7 entities"), /*#__PURE__*/React.createElement("span", null, "ECS \xB7 14 systems"), /*#__PURE__*/React.createElement("span", null, "pymunk 6.6"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 'auto'
    }
  }, "F12 toggles all tools")));
}
function EditorApp() {
  const D = window.EditorData;
  const [theme, setTheme] = React.useState('dark');
  const [sel, setSel] = React.useState(D.entities[0].id);
  const [filter, setFilter] = React.useState('');
  const [menu, setMenu] = React.useState(null);
  const [res, setRes] = React.useState(null);
  const [gizmos, setGizmos] = React.useState(true);
  const [zoom, setZoom] = React.useState(2);
  const [tools, setTools] = React.useState({
    'Performance Monitor': true,
    'Physics Debugger': true,
    'Event Monitor': false,
    'Shortcuts Panel (This)': false
  });
  const toggleTool = n => setTools(t => ({
    ...t,
    [n]: !t[n]
  }));
  React.useEffect(() => {
    const h = e => {
      const map = {
        F1: 'Performance Monitor',
        F2: 'Entity Inspector',
        F3: 'Event Monitor',
        F4: 'Physics Debugger',
        F8: 'Shortcuts Panel (This)'
      };
      if (map[e.key]) {
        e.preventDefault();
        toggleTool(map[e.key]);
      }
      if (e.key === 'F12') {
        e.preventDefault();
        setTools(t => {
          const any = Object.values(t).some(Boolean);
          const o = {};
          for (const k in t) o[k] = !any;
          return o;
        });
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  const entity = D.entities.find(e => e.id === sel);
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": theme === 'light' ? 'light' : undefined,
    style: {
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface-page)',
      color: 'var(--text-body)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement(MenuBar, {
    theme: theme,
    onTheme: () => setTheme(t => t === 'light' ? 'dark' : 'light'),
    menu: menu,
    onMenu: setMenu,
    tools: tools,
    toggleTool: toggleTool
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      position: 'relative',
      display: 'grid',
      gridTemplateColumns: '232px minmax(0,1fr) 268px',
      gridTemplateRows: 'minmax(0,1fr) 176px',
      gridTemplateAreas: '"left view right" "assets assets right"',
      gap: 6,
      padding: 6
    }
  }, /*#__PURE__*/React.createElement(window.HierarchyPanel, {
    entities: D.entities,
    selected: sel,
    onSelect: setSel,
    filter: filter,
    onFilter: setFilter
  }), /*#__PURE__*/React.createElement(Viewport, {
    tools: tools,
    gizmos: gizmos,
    onGizmos: setGizmos,
    zoom: zoom,
    onZoom: setZoom
  }), /*#__PURE__*/React.createElement(window.InspectorPanel, {
    entity: entity
  }), /*#__PURE__*/React.createElement(window.AssetsPanel, {
    selected: res,
    onSelect: setRes
  }), /*#__PURE__*/React.createElement(window.ResourceInspector, {
    path: res,
    onClose: () => setRes(null)
  }), tools['Shortcuts Panel (This)'] && /*#__PURE__*/React.createElement(window.ShortcutsPanel, {
    onClose: () => toggleTool('Shortcuts Panel (This)')
  })));
}
Object.assign(window, {
  EditorApp,
  MenuBar,
  Viewport
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/editor/EditorShell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/editor/editor-data.js
try { (() => {
window.EditorData = {
  entities: [{
    id: '0a3f91c2',
    tag: 'guara_player',
    src: 'res://prefabs/guara_player.json',
    comps: {
      Transform: {
        position: '(320.0, 448.0)',
        rotation: '0.0',
        scale: '(1.0, 1.0)'
      },
      RigidBody: {
        mass: '12.0',
        body_type: 'DYNAMIC',
        friction: '0.85',
        gravity_scale: '1.0'
      },
      Collider: {
        shape: 'BOX',
        size: '(28.0, 40.0)',
        offset: '(0.0, -4.0)',
        is_sensor: 'False'
      },
      Sprite: {
        texture: 'guara_atlas',
        layer: '10',
        flip_x: 'False',
        tint: '(255, 255, 255, 255)'
      },
      Animation: {
        clip: 'idle',
        fps: '12',
        loop: 'True'
      },
      PlatformerController: {
        move_speed: '240.0',
        jump_force: '560.0',
        coyote_time: '0.12'
      }
    }
  }, {
    id: '6c1d40ab',
    tag: 'falcao_companion',
    src: 'res://prefabs/falcao.json',
    comps: {
      Transform: {
        position: '(356.0, 402.0)',
        rotation: '0.0',
        scale: '(1.0, 1.0)'
      },
      Sprite: {
        texture: 'falcao_atlas',
        layer: '11',
        flip_x: 'False',
        tint: '(255, 255, 255, 255)'
      },
      Animation: {
        clip: 'hover',
        fps: '12',
        loop: 'True'
      },
      SteeringAgent: {
        behavior: 'FOLLOW',
        max_speed: '300.0',
        arrive_radius: '48.0'
      }
    }
  }, {
    id: 'b208ee71',
    tag: 'roca_platform_03',
    src: 'res://levels/roca_01.json',
    comps: {
      Transform: {
        position: '(704.0, 512.0)',
        rotation: '0.0',
        scale: '(2.0, 1.0)'
      },
      RigidBody: {
        mass: '0.0',
        body_type: 'STATIC',
        friction: '1.0',
        gravity_scale: '0.0'
      },
      Collider: {
        shape: 'BOX',
        size: '(128.0, 32.0)',
        offset: '(0.0, 0.0)',
        is_sensor: 'False'
      }
    }
  }, {
    id: 'ff40a9d5',
    tag: 'gear_hazard_01',
    comps: {
      Transform: {
        position: '(928.0, 480.0)',
        rotation: '14.0',
        scale: '(1.0, 1.0)'
      },
      Collider: {
        shape: 'CIRCLE',
        size: '(20.0, 20.0)',
        offset: '(0.0, 0.0)',
        is_sensor: 'True'
      },
      TriggerVolume: {
        on_enter: 'damage_player',
        once: 'False'
      }
    }
  }, {
    id: '3e77b104',
    tag: 'fruit_pickup_07',
    comps: {
      Transform: {
        position: '(512.0, 416.0)',
        rotation: '0.0',
        scale: '(1.0, 1.0)'
      },
      Sprite: {
        texture: 'items_atlas',
        layer: '8',
        flip_x: 'False',
        tint: '(255, 255, 255, 255)'
      },
      TriggerVolume: {
        on_enter: 'collect_fruit',
        once: 'True'
      }
    }
  }, {
    id: '91ba2cf0',
    tag: 'main_camera',
    comps: {
      Transform: {
        position: '(320.0, 448.0)',
        rotation: '0.0',
        scale: '(1.0, 1.0)'
      },
      Camera: {
        zoom: '2.0',
        follow_target: 'guara_player',
        deadzone: '(48.0, 32.0)'
      }
    }
  }, {
    id: 'c40d18e3',
    comps: {
      Transform: {
        position: '(0.0, 0.0)',
        rotation: '0.0',
        scale: '(1.0, 1.0)'
      },
      AmbientLight: {
        color: '(255, 214, 150, 255)',
        intensity: '0.85'
      }
    }
  }],
  registry: ['guara_player.json -> res://prefabs/guara_player.json', 'falcao.json -> res://prefabs/falcao.json', 'roca_01.json -> res://levels/roca_01.json', 'cerrado_ground.tsx -> res://tiles/cerrado_ground.tsx', 'theme_cerrado.json -> res://ui/theme_cerrado.json'],
  cache: [['DataResource', 'guara_player.json', 'res://prefabs/guara_player.json'], ['DataResource', 'roca_01.json', 'res://levels/roca_01.json'], ['TextureResource', 'guara_atlas.png', 'res://atlas/guara_atlas.png'], ['TextureResource', 'cerrado_tiles.png', 'res://atlas/cerrado_tiles.png'], ['AudioResource', 'wind_loop.ogg', 'res://audio/wind_loop.ogg'], ['DataResource', 'theme_cerrado.json', 'res://ui/theme_cerrado.json']],
  shortcuts: [['F1', 'Performance Monitor'], ['F2', 'Entity Inspector'], ['F3', 'Event Monitor'], ['F4', 'Physics Debugger'], ['F5', 'Robust ImGui Editor'], ['F8', 'Shortcuts Panel (This)'], ['F12', 'Toggle ALL Tools']],
  events: [['12.481', 'PhysicsStepEvent', 'dt=0.0167'], ['12.483', 'CollisionEnterEvent', 'guara_player ↔ roca_platform_03'], ['12.501', 'AnimationClipChanged', 'guara_player: idle → run'], ['12.540', 'TriggerEnterEvent', 'fruit_pickup_07'], ['12.541', 'ResourceLoaded', 'res://audio/pickup.ogg'], ['12.612', 'InputActionEvent', 'jump (pressed)'], ['12.613', 'PlatformerJumpEvent', 'force=560.0']]
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/editor/editor-data.js", error: String((e && e.message) || e) }); }

// ui_kits/game/GameScreens-standalone.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  Checkbox,
  Slider,
  ProgressBar,
  Image: DSImage,
  BoxContainer,
  Canvas: DSCanvas
} = window.PyguaraDesignSystem_ca79d7;
const A = '../../assets/'; /* standalone copy: image srcs come from window.__resources (see index-standalone.html meta tags) */

/* Every game screen is a WINDOW onto the one key-art illustration — never a
   recomposited plate. `scene-window-grove.png` is a 16:9 crop cut straight
   from it — grove, plank platform, water, Guará running, and no wordmark, so
   the transparent lockup can be overlaid on the title screen without
   duplicating a sign. (`scene-window-sign.png` is the complementary crop for
   surfaces that want the carved lockup baked in.) Aspect-matched crops, not
   object-position — the source aspect is too close to 16:9 to pan. */
function World({
  children,
  dim = 0
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      width: '100%',
      height: '100%',
      overflow: 'hidden',
      background: 'var(--sky-500)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources.sceneGrove,
    alt: "",
    style: {
      position: 'absolute',
      inset: 0,
      width: '100%',
      height: '100%',
      objectFit: 'cover'
    }
  }), dim > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      background: 'var(--surface-scrim)',
      opacity: dim
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0
    }
  }, children));
}
function TitleScreen({
  onPlay,
  onOptions
}) {
  return /*#__PURE__*/React.createElement(World, {
    dim: .5
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 18,
      padding: '20px 0',
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources.logoLockup,
    alt: "Pyguara Solar Engine \u2014 Guar\xE1 & Falc\xE3o",
    style: {
      maxHeight: '36%',
      maxWidth: '62%',
      width: 'auto',
      height: 'auto',
      minHeight: 0,
      flex: '0 1 auto',
      objectFit: 'contain'
    }
  }), /*#__PURE__*/React.createElement(BoxContainer, {
    direction: "VERTICAL",
    align: "CENTER",
    spacing: 12
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Play",
    variant: "sage",
    size: "large",
    onClick: onPlay,
    style: {
      minWidth: 230
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Options",
    variant: "wood",
    size: "large",
    onClick: onOptions,
    style: {
      minWidth: 230
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Quit",
    variant: "wood",
    size: "large",
    style: {
      minWidth: 230
    }
  })), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 1,
    padding: "7px 11px",
    style: {
      background: 'var(--surface-card)',
      marginTop: 2,
      whiteSpace: 'nowrap',
      flex: '0 0 auto'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Built on Pyguara",
    fontSize: 12,
    color: "var(--text-body)"
  }))));
}

/* HUD: health and stamina meters, fruit counter, falcão charges, all engine primitives. */
function Hud({
  fruit,
  health,
  stamina,
  charges
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: 20,
      top: 18,
      display: 'flex',
      flexDirection: 'column',
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "8px 10px",
    bevel: true,
    style: {
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources.avatarGuara,
    alt: "",
    style: {
      height: 32,
      width: 'auto'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 5
    }
  }, /*#__PURE__*/React.createElement(ProgressBar, {
    value: health,
    width: 168,
    height: 14,
    fillColor: "var(--state-danger)"
  }), /*#__PURE__*/React.createElement(ProgressBar, {
    value: stamina,
    width: 168,
    height: 9,
    fillColor: "var(--state-warn)"
  })))), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "6px 10px",
    style: {
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources.avatarFalcao,
    alt: "",
    style: {
      height: 26,
      width: 'auto'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4
    }
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 11,
      height: 11,
      background: i < charges ? 'var(--falcao-400)' : 'transparent',
      border: '1px solid var(--falcao-400)',
      display: 'block'
    }
  })))))), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "7px 12px",
    bevel: true,
    style: {
      position: 'absolute',
      right: 20,
      top: 18,
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 20,
      height: 20,
      borderRadius: '50%',
      background: 'var(--gold-500)',
      border: '2px solid var(--terra-500)',
      display: 'block'
    }
  }), /*#__PURE__*/React.createElement(Label, {
    text: String(fruit).padStart(2, '0') + ' / 24',
    font: "pixel",
    fontSize: 16,
    color: "var(--sand-100)"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '50%',
      bottom: 16,
      transform: 'translateX(-50%)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources.keycaps,
    alt: "Move, jump and call Falc\xE3o",
    style: {
      height: 44,
      imageRendering: 'pixelated',
      opacity: .9
    }
  })));
}
function PlayScreen({
  onPause,
  fruit,
  onCollect
}) {
  return /*#__PURE__*/React.createElement(World, null, /*#__PURE__*/React.createElement(Hud, {
    fruit: fruit,
    health: .72,
    stamina: .45,
    charges: 2
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onCollect,
    title: "Collect the hanging fruit",
    style: {
      position: 'absolute',
      left: '32.5%',
      top: '22%',
      width: 34,
      height: 34,
      borderRadius: '50%',
      background: 'transparent',
      border: '2px solid var(--ink-900)',
      cursor: 'pointer',
      boxShadow: 'inset 0 0 0 2px var(--sand-100), 0 0 0 2px var(--sand-100), 0 0 0 5px rgba(30,18,12,.45)'
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Pause",
    variant: "ghost",
    size: "small",
    onClick: onPause,
    style: {
      position: 'absolute',
      right: 20,
      bottom: 18,
      background: 'var(--surface-overlay)'
    }
  }));
}
function PauseScreen({
  onResume,
  onOptions,
  onTitle
}) {
  return /*#__PURE__*/React.createElement(World, {
    dim: .62
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      display: 'grid',
      placeItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 3,
    padding: "26px 30px",
    bevel: true,
    style: {
      minWidth: 330,
      boxShadow: 'var(--shadow-stamp-lg)'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "PAUSED",
    font: "display",
    fontSize: 22,
    color: "var(--action-secondary)",
    style: {
      textAlign: 'center'
    }
  }), /*#__PURE__*/React.createElement(BoxContainer, {
    direction: "VERTICAL",
    align: "CENTER",
    spacing: 10,
    style: {
      marginTop: 22
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Resume",
    variant: "sage",
    onClick: onResume,
    style: {
      minWidth: 220
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Options",
    variant: "wood",
    onClick: onOptions,
    style: {
      minWidth: 220
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Quit to Title",
    variant: "wood",
    onClick: onTitle,
    style: {
      minWidth: 220
    }
  })))));
}
function OptionsScreen({
  onBack
}) {
  const [master, setMaster] = React.useState(.8),
    [music, setMusic] = React.useState(.55),
    [sfx, setSfx] = React.useState(.7);
  const [full, setFull] = React.useState(true),
    [vsync, setVsync] = React.useState(true),
    [shake, setShake] = React.useState(false),
    [colliders, setColliders] = React.useState(false);
  const Row = ({
    label,
    children
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '132px 1fr',
      alignItems: 'center',
      gap: 14,
      padding: '7px 0',
      borderBottom: '1px solid var(--edge-subtle)'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: label,
    fontSize: 12,
    color: "var(--text-muted)"
  }), children);
  return /*#__PURE__*/React.createElement(World, {
    dim: .7
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      display: 'grid',
      placeItems: 'center',
      padding: 20,
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 3,
    padding: "24px 28px",
    bevel: true,
    style: {
      width: 'min(520px,94%)',
      boxShadow: 'var(--shadow-stamp-lg)'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "OPTIONS",
    font: "display",
    fontSize: 18,
    color: "var(--action-secondary)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Audio",
    font: "pixel",
    fontSize: 14,
    color: "var(--text-heading)"
  }), /*#__PURE__*/React.createElement(Row, {
    label: "Master"
  }, /*#__PURE__*/React.createElement(Slider, {
    value: master,
    onChange: setMaster,
    width: 200,
    showValue: true
  })), /*#__PURE__*/React.createElement(Row, {
    label: "Music"
  }, /*#__PURE__*/React.createElement(Slider, {
    value: music,
    onChange: setMusic,
    width: 200,
    showValue: true
  })), /*#__PURE__*/React.createElement(Row, {
    label: "Effects"
  }, /*#__PURE__*/React.createElement(Slider, {
    value: sfx,
    onChange: setSfx,
    width: 200,
    showValue: true
  })), /*#__PURE__*/React.createElement(Label, {
    text: "Display",
    font: "pixel",
    fontSize: 14,
    color: "var(--text-heading)",
    style: {
      marginTop: 16
    }
  }), /*#__PURE__*/React.createElement(Row, {
    label: "Fullscreen"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: full ? 'On' : 'Off',
    checked: full,
    onChange: setFull
  })), /*#__PURE__*/React.createElement(Row, {
    label: "V-Sync"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: vsync ? 'On' : 'Off',
    checked: vsync,
    onChange: setVsync
  })), /*#__PURE__*/React.createElement(Row, {
    label: "Screen shake"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: shake ? 'On' : 'Off',
    checked: shake,
    onChange: setShake
  })), /*#__PURE__*/React.createElement(Label, {
    text: "Developer",
    font: "pixel",
    fontSize: 14,
    color: "var(--text-heading)",
    style: {
      marginTop: 16
    }
  }), /*#__PURE__*/React.createElement(Row, {
    label: "Show colliders"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: colliders ? 'On' : 'Off',
    checked: colliders,
    onChange: setColliders
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      marginTop: 20
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Back",
    variant: "sage",
    onClick: onBack
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Defaults",
    variant: "ghost"
  })))));
}
function GameApp() {
  const [screen, setScreen] = React.useState('title');
  const [fruit, setFruit] = React.useState(7);
  const [prev, setPrev] = React.useState('title');
  const go = s => {
    setPrev(screen);
    setScreen(s);
  };
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": "game",
    style: {
      width: '100%',
      height: '100vh',
      background: 'var(--ink-900)'
    }
  }, screen === 'title' && /*#__PURE__*/React.createElement(TitleScreen, {
    onPlay: () => go('play'),
    onOptions: () => go('options')
  }), screen === 'play' && /*#__PURE__*/React.createElement(PlayScreen, {
    onPause: () => go('pause'),
    fruit: fruit,
    onCollect: () => setFruit(n => Math.min(24, n + 1))
  }), screen === 'pause' && /*#__PURE__*/React.createElement(PauseScreen, {
    onResume: () => go('play'),
    onOptions: () => go('options'),
    onTitle: () => go('title')
  }), screen === 'options' && /*#__PURE__*/React.createElement(OptionsScreen, {
    onBack: () => go(prev === 'options' ? 'title' : prev)
  }));
}
Object.assign(window, {
  GameApp,
  TitleScreen,
  PlayScreen,
  PauseScreen,
  OptionsScreen,
  Hud,
  World
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/game/GameScreens-standalone.jsx", error: String((e && e.message) || e) }); }

// ui_kits/game/GameScreens.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  Checkbox,
  Slider,
  ProgressBar,
  Image: DSImage,
  BoxContainer,
  Canvas: DSCanvas
} = window.PyguaraDesignSystem_ca79d7;
const A = '../../assets/';

/* Every game screen is a WINDOW onto the one key-art illustration — never a
   recomposited plate. `scene-window-grove.png` is a 16:9 crop cut straight
   from it — grove, plank platform, water, Guará running, and no wordmark, so
   the transparent lockup can be overlaid on the title screen without
   duplicating a sign. (`scene-window-sign.png` is the complementary crop for
   surfaces that want the carved lockup baked in.) Aspect-matched crops, not
   object-position — the source aspect is too close to 16:9 to pan. */
function World({
  children,
  dim = 0
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      width: '100%',
      height: '100%',
      overflow: 'hidden',
      background: 'var(--sky-500)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/scene-window-grove.png',
    alt: "",
    style: {
      position: 'absolute',
      inset: 0,
      width: '100%',
      height: '100%',
      objectFit: 'cover'
    }
  }), dim > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      background: 'var(--surface-scrim)',
      opacity: dim
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0
    }
  }, children));
}
function TitleScreen({
  onPlay,
  onOptions
}) {
  return /*#__PURE__*/React.createElement(World, {
    dim: .5
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 18,
      padding: '20px 0',
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/logo-pyguara-lockup.png',
    alt: "Pyguara Solar Engine \u2014 Guar\xE1 & Falc\xE3o",
    style: {
      maxHeight: '36%',
      maxWidth: '62%',
      width: 'auto',
      height: 'auto',
      minHeight: 0,
      flex: '0 1 auto',
      objectFit: 'contain'
    }
  }), /*#__PURE__*/React.createElement(BoxContainer, {
    direction: "VERTICAL",
    align: "CENTER",
    spacing: 12
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Play",
    variant: "sage",
    size: "large",
    onClick: onPlay,
    style: {
      minWidth: 230
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Options",
    variant: "wood",
    size: "large",
    onClick: onOptions,
    style: {
      minWidth: 230
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Quit",
    variant: "wood",
    size: "large",
    style: {
      minWidth: 230
    }
  })), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 1,
    padding: "7px 11px",
    style: {
      background: 'var(--surface-card)',
      marginTop: 2,
      whiteSpace: 'nowrap',
      flex: '0 0 auto'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Built on Pyguara",
    fontSize: 12,
    color: "var(--text-body)"
  }))));
}

/* HUD: health and stamina meters, fruit counter, falcão charges, all engine primitives. */
function Hud({
  fruit,
  health,
  stamina,
  charges
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: 20,
      top: 18,
      display: 'flex',
      flexDirection: 'column',
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "8px 10px",
    bevel: true,
    style: {
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/avatar-guara.png',
    alt: "",
    style: {
      height: 32,
      width: 'auto'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 5
    }
  }, /*#__PURE__*/React.createElement(ProgressBar, {
    value: health,
    width: 168,
    height: 14,
    fillColor: "var(--state-danger)"
  }), /*#__PURE__*/React.createElement(ProgressBar, {
    value: stamina,
    width: 168,
    height: 9,
    fillColor: "var(--state-warn)"
  })))), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "6px 10px",
    style: {
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/avatar-falcao.png',
    alt: "",
    style: {
      height: 26,
      width: 'auto'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4
    }
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 11,
      height: 11,
      background: i < charges ? 'var(--falcao-400)' : 'transparent',
      border: '1px solid var(--falcao-400)',
      display: 'block'
    }
  })))))), /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "7px 12px",
    bevel: true,
    style: {
      position: 'absolute',
      right: 20,
      top: 18,
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 20,
      height: 20,
      borderRadius: '50%',
      background: 'var(--gold-500)',
      border: '2px solid var(--terra-500)',
      display: 'block'
    }
  }), /*#__PURE__*/React.createElement(Label, {
    text: String(fruit).padStart(2, '0') + ' / 24',
    font: "pixel",
    fontSize: 16,
    color: "var(--sand-100)"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: '50%',
      bottom: 16,
      transform: 'translateX(-50%)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'sprites/keycaps.png',
    alt: "Move, jump and call Falc\xE3o",
    style: {
      height: 44,
      imageRendering: 'pixelated',
      opacity: .9
    }
  })));
}
function PlayScreen({
  onPause,
  fruit,
  onCollect
}) {
  return /*#__PURE__*/React.createElement(World, null, /*#__PURE__*/React.createElement(Hud, {
    fruit: fruit,
    health: .72,
    stamina: .45,
    charges: 2
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onCollect,
    title: "Collect the hanging fruit",
    style: {
      position: 'absolute',
      left: '32.5%',
      top: '22%',
      width: 34,
      height: 34,
      borderRadius: '50%',
      background: 'transparent',
      border: '2px solid var(--ink-900)',
      cursor: 'pointer',
      boxShadow: 'inset 0 0 0 2px var(--sand-100), 0 0 0 2px var(--sand-100), 0 0 0 5px rgba(30,18,12,.45)'
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Pause",
    variant: "ghost",
    size: "small",
    onClick: onPause,
    style: {
      position: 'absolute',
      right: 20,
      bottom: 18,
      background: 'var(--surface-overlay)'
    }
  }));
}
function PauseScreen({
  onResume,
  onOptions,
  onTitle
}) {
  return /*#__PURE__*/React.createElement(World, {
    dim: .62
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      display: 'grid',
      placeItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 3,
    padding: "26px 30px",
    bevel: true,
    style: {
      minWidth: 330,
      boxShadow: 'var(--shadow-stamp-lg)'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "PAUSED",
    font: "display",
    fontSize: 22,
    color: "var(--action-secondary)",
    style: {
      textAlign: 'center'
    }
  }), /*#__PURE__*/React.createElement(BoxContainer, {
    direction: "VERTICAL",
    align: "CENTER",
    spacing: 10,
    style: {
      marginTop: 22
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Resume",
    variant: "sage",
    onClick: onResume,
    style: {
      minWidth: 220
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Options",
    variant: "wood",
    onClick: onOptions,
    style: {
      minWidth: 220
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Quit to Title",
    variant: "wood",
    onClick: onTitle,
    style: {
      minWidth: 220
    }
  })))));
}
function OptionsScreen({
  onBack
}) {
  const [master, setMaster] = React.useState(.8),
    [music, setMusic] = React.useState(.55),
    [sfx, setSfx] = React.useState(.7);
  const [full, setFull] = React.useState(true),
    [vsync, setVsync] = React.useState(true),
    [shake, setShake] = React.useState(false),
    [colliders, setColliders] = React.useState(false);
  const Row = ({
    label,
    children
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '132px 1fr',
      alignItems: 'center',
      gap: 14,
      padding: '7px 0',
      borderBottom: '1px solid var(--edge-subtle)'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: label,
    fontSize: 12,
    color: "var(--text-muted)"
  }), children);
  return /*#__PURE__*/React.createElement(World, {
    dim: .7
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      display: 'grid',
      placeItems: 'center',
      padding: 20,
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 3,
    padding: "24px 28px",
    bevel: true,
    style: {
      width: 'min(520px,94%)',
      boxShadow: 'var(--shadow-stamp-lg)'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "OPTIONS",
    font: "display",
    fontSize: 18,
    color: "var(--action-secondary)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Audio",
    font: "pixel",
    fontSize: 14,
    color: "var(--text-heading)"
  }), /*#__PURE__*/React.createElement(Row, {
    label: "Master"
  }, /*#__PURE__*/React.createElement(Slider, {
    value: master,
    onChange: setMaster,
    width: 200,
    showValue: true
  })), /*#__PURE__*/React.createElement(Row, {
    label: "Music"
  }, /*#__PURE__*/React.createElement(Slider, {
    value: music,
    onChange: setMusic,
    width: 200,
    showValue: true
  })), /*#__PURE__*/React.createElement(Row, {
    label: "Effects"
  }, /*#__PURE__*/React.createElement(Slider, {
    value: sfx,
    onChange: setSfx,
    width: 200,
    showValue: true
  })), /*#__PURE__*/React.createElement(Label, {
    text: "Display",
    font: "pixel",
    fontSize: 14,
    color: "var(--text-heading)",
    style: {
      marginTop: 16
    }
  }), /*#__PURE__*/React.createElement(Row, {
    label: "Fullscreen"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: full ? 'On' : 'Off',
    checked: full,
    onChange: setFull
  })), /*#__PURE__*/React.createElement(Row, {
    label: "V-Sync"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: vsync ? 'On' : 'Off',
    checked: vsync,
    onChange: setVsync
  })), /*#__PURE__*/React.createElement(Row, {
    label: "Screen shake"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: shake ? 'On' : 'Off',
    checked: shake,
    onChange: setShake
  })), /*#__PURE__*/React.createElement(Label, {
    text: "Developer",
    font: "pixel",
    fontSize: 14,
    color: "var(--text-heading)",
    style: {
      marginTop: 16
    }
  }), /*#__PURE__*/React.createElement(Row, {
    label: "Show colliders"
  }, /*#__PURE__*/React.createElement(Checkbox, {
    label: colliders ? 'On' : 'Off',
    checked: colliders,
    onChange: setColliders
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      marginTop: 20
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Back",
    variant: "sage",
    onClick: onBack
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Defaults",
    variant: "ghost"
  })))));
}
function GameApp() {
  const [screen, setScreen] = React.useState('title');
  const [fruit, setFruit] = React.useState(7);
  const [prev, setPrev] = React.useState('title');
  const go = s => {
    setPrev(screen);
    setScreen(s);
  };
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": "game",
    style: {
      width: '100%',
      height: '100vh',
      background: 'var(--ink-900)'
    }
  }, screen === 'title' && /*#__PURE__*/React.createElement(TitleScreen, {
    onPlay: () => go('play'),
    onOptions: () => go('options')
  }), screen === 'play' && /*#__PURE__*/React.createElement(PlayScreen, {
    onPause: () => go('pause'),
    fruit: fruit,
    onCollect: () => setFruit(n => Math.min(24, n + 1))
  }), screen === 'pause' && /*#__PURE__*/React.createElement(PauseScreen, {
    onResume: () => go('play'),
    onOptions: () => go('options'),
    onTitle: () => go('title')
  }), screen === 'options' && /*#__PURE__*/React.createElement(OptionsScreen, {
    onBack: () => go(prev === 'options' ? 'title' : prev)
  }));
}
Object.assign(window, {
  GameApp,
  TitleScreen,
  PlayScreen,
  PauseScreen,
  OptionsScreen,
  Hud,
  World
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/game/GameScreens.jsx", error: String((e && e.message) || e) }); }

// ui_kits/game/doc-page.js
try { (() => {
// @ds-adherence-ignore -- omelette starter scaffold (raw elements/hex/px by design)
// Copied omelette starter. Re-running copy_starter_component with this kind overwrites this file with the latest version (page content is unaffected).
/* BEGIN USAGE */
/**
 * <doc-page> — paged-document shell for printable HTML.
 *
 * FIRST, decide how the document paginates — up front, before building:
 *
 * - FLOWING document (the default): write the whole document as one
 *   normal HTML flow inside <doc-page>; the browser's print engine
 *   splits it onto pages at export. Use for long-form documents with a
 *   single text flow: reports, memos, letters, essays.
 * - EXPLICIT pagination: a fixed set of pre-paginated pages, one
 *   <section class="page"> child per page. Use when the user asks for a
 *   specific page count, or the design implies one: a one-page resume, a
 *   two-sided flier, a poster, a certificate, a brochure — any richly
 *   laid-out document without a single text flow.
 * - If in doubt, ask the user as part of the build.
 *
 * PAGE SIZING — paper differs by country (letter vs A4), so the printed
 * sheet is not one fixed truth:
 * - FLOWING documents pin NO paper size: the print engine paginates
 *   onto the user's real paper, and the content reflows to it.
 * - EXPLICITLY PAGINATED documents print each page at a FIXED page box
 *   with overflow hidden — letter by default, size="a4" for a clearly
 *   metric user, the user's chosen paper when they export. Design each
 *   page to FILL that box, fitting letter and A4 alike without overlap.
 * - width/height pin an explicit fixed size, ONLY when the user gives
 *   one.
 * Never write your own @page rule or hard-code paper dimensions in the
 * content.
 *
 * Sizing modes (attributes):
 *   (none)                      — portrait: flowing docs use the user's
 *           paper; explicitly paginated pages use the named size box
 *           (letter unless size="a4")
 *   orientation="landscape"     — the same, landscape
 *   width / height              — explicit fixed size, ONLY when the user
 *           gives one (e.g. width="22in" height="30in" for a 22×30
 *           poster): the page IS the design's size, printed at true
 *           dimensions (or scaled onto the user's paper at print time).
 *           Any absolute CSS length: px/in/mm/cm/pt/pc.
 * The component announces the chosen mode to the host app at runtime (a
 * meta tag it injects), so the print path can inject the user's true
 * paper size.
 *
 * On screen the document renders on a desk background: a flowing
 * document as one tall scrolling sheet (Google Docs' pageless view);
 * explicitly paginated documents as one card per page.
 *
 * EXPLICIT pagination usage:
 *   <style>doc-page:not(:defined){visibility:hidden}<\/style>
 *   <doc-page>
 *     <section class="page" id="p1">…one page's design…<\/section>
 *     <section class="page" id="p2">…<\/section>
 *   <\/doc-page>
 *   <script src="doc-page.js"><\/script>
 * How the page box works, concretely: each .page prints as ONE full-bleed
 * sheet at a FIXED physical size — letter by default (set size="a4" for
 * a clearly metric user), the user's chosen paper when they export —
 * with overflow hidden. Nothing scrolls and nothing reflows onto a next
 * sheet: content that misses the box is CLIPPED. Design each page to
 * FILL that page box, and to fit it — letter and A4 alike — without
 * overlap. Each page is a size container; don't size anything in
 * viewport units (they track the window, not the page), and never set
 * width or height on the .page section itself (the component sizes the
 * page box; an authored height like 100% is meaningless at print and is
 * overridden). The component owns the page box, the screen card chrome,
 * and the page breaks (never add your own break-before/after). Don't mix
 * .page sections with flowing content or header/footer slots in the same
 * document.
 *
 * FLOWING usage:
 *   <style>doc-page:not(:defined){visibility:hidden}<\/style>
 *   <doc-page margin="0.75in">
 *     <h1>Title<\/h1>
 *     <p>…body…<\/p>
 *   <\/doc-page>
 *   <script src="doc-page.js"><\/script>
 * There is no manual page-splitting — the browser's print engine
 * paginates at export. Standard break-hygiene rules (`break-inside:
 * avoid` on figures, code blocks, images and table rows; `orphans/
 * widows: 3`) are applied so paragraphs and groups split cleanly. On
 * screen and at print, headings default to `text-wrap: balance` and
 * body text to `text-wrap: pretty`; the defaults have zero specificity,
 * so any text-wrap you declare wins.
 *
 * Other attributes:
 *   size    — letter | a4 | legal (default letter). Flowing documents:
 *           preview proportion only — it does NOT pin their printed
 *           paper (the print dialog's paper governs); leave it alone
 *           there. Explicitly paginated documents: it sets the page box
 *           the cards and the pinned @page share (the export dialog's
 *           choice overrides both at print) — set size="a4" for a
 *           clearly metric user. Scaled-fit: names the sheet the fit is
 *           computed against, same a4-for-metric-users advice.
 *   content-width / content-height — the design's own fixed dimensions
 *           (CSS lengths), for scaling a fixed-size design ONTO the
 *           named sheet: content lays out at exactly this size, and the
 *           component scales it to fit that sheet's printable area
 *           (centered horizontally, top-aligned; the export dialog
 *           re-fits to the user's actual paper choice where available).
 *           Both must be set; they do not change the page box. For pages
 *           WITHOUT running header/footer slots.
 *   margin  — printable inset on every page of a FLOWING document
 *           (default 0.75in); margin="0" makes pages full-bleed.
 *           Explicitly paginated pages are always full-bleed.
 *
 * Running header/footer (flowing documents only): give an element
 * `slot="header"` or `slot="footer"` and it repeats on every printed
 * page via `position: fixed`. To keep body text from sliding under it,
 * the component prints inside a single-cell table whose <thead>/<tfoot>
 * are spacers sized to the header/footer height — browsers repeat
 * thead/tfoot on every page, so each sheet's content starts below the
 * header and ends above the footer. On screen the header/footer render
 * once at the top/bottom of the sheet.
 *
 * At print the component injects `@page { margin: 0 }` (which leaves
 * Chrome no margin box to draw its date/URL/page-count header in) and
 * moves the visual margin onto the sheet's own padding. It also marks
 * the document as owning its print CSS (a
 * `meta[name="omelette-owns-print"]` it injects at runtime), so the
 * PDF export never injects page-geometry CSS of its own on top.
 *
 * Print best practices for the content you author:
 * - Multi-column text: use CSS columns (`column-count` +
 *   `column-gap`), never side-by-side flex/grid columns — only real
 *   CSS columns flow and break across pages. `column-span: all` lets
 *   a heading span the columns; `hyphens: auto` (needs `lang` on
 *   the html element) keeps narrow columns readable.
 * - Page breaks in flowing documents: `break-before: page` on an
 *   element that must start a new page (a chapter, an appendix). Add
 *   your own kept-together blocks (callouts, stat tiles, cards) to a
 *   `break-inside: avoid` rule, and keep each one shorter than a page.
 * - Extend `orphans: 3; widows: 3` to any custom text blocks you add
 *   (p and li are covered by default).
 * - Give long tables a <thead> — browsers repeat it on every printed
 *   page.
 * - No `position: fixed`/`sticky` and no viewport units in content:
 *   fixed elements stamp every printed page (running headers/footers go
 *   in the component's slots) and `100vh` mis-sizes at print.
 *
 * Author content as static HTML so the user can click-to-edit any text
 * directly. Do not set width/padding/background on the document body —
 * the component owns the sheet box.
 */
/* END USAGE */

(() => {
  const PAPER = {
    letter: ['8.5in', '11in'],
    a4: ['210mm', '297mm'],
    legal: ['8.5in', '14in']
  };
  const CSS_LENGTH = /^\d+(\.\d+)?(px|in|mm|cm|pt|pc)$/;
  // Unitless "0" is a valid CSS length and the natural way to write
  // margin="0"; normalise it to 0px so max()/calc() (which reject a bare
  // number) keep working.
  const safeLen = (v, fb) => {
    v = (v || '').trim();
    return v === '0' ? '0px' : CSS_LENGTH.test(v) ? v : fb;
  };
  // WebKit (Safari and every iOS browser shell) never repeats a table's
  // thead/tfoot on printed pages (WebKit bug 17205), so the spacer-borne
  // vertical margins of a FLOWING document reach only the first page
  // there. Engine check, not browser check: vendor is 'Apple Computer,
  // Inc.' exactly for WebKit and 'Google Inc.' for Blink.
  const WK_PRINT = /apple/i.test(navigator.vendor || '');
  // CSS length → px number (CSS absolute units are exact: 1in = 96px).
  // Returns NaN for anything safeLen would reject — callers gate on it.
  const PX_PER = {
    px: 1,
    in: 96,
    mm: 96 / 25.4,
    cm: 96 / 2.54,
    pt: 96 / 72,
    pc: 16
  };
  const toPx = v => {
    const m = /^(\d+(?:\.\d+)?)(px|in|mm|cm|pt|pc)$/.exec((v || '').trim());
    return m ? parseFloat(m[1]) * PX_PER[m[2]] : NaN;
  };
  const stylesheet = `
    :host {
      position: relative;
      display: block;
      /* When the viewport is narrower than the page, grow to wrap the
       * sheet (plus this padding) instead of staying viewport-width, so
       * the desk background and right margin reach the sheet's far edge
       * in the horizontal scroll. */
      min-width: max-content;
      min-height: 100vh;
      background: #f5f5f4;
      padding: 48px 24px;
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      --doc-page-w: 8.5in;
      --doc-page-h: 11in;
      --doc-page-margin: 0.75in;
      --doc-hdr-h: 0px;
      --doc-ftr-h: 0px;
      --doc-hdr-pad: 0px;
      --doc-ftr-pad: 0px;
    }
    .sheet {
      width: var(--doc-page-w);
      margin: 0 auto;
      background: #fff;
      box-shadow: 0 2px 10px rgba(20, 20, 19, 0.12);
      border-radius: 7px;
      box-sizing: border-box;
      padding: var(--doc-page-margin);
    }
    .frame { width: 100%; border-collapse: collapse; }
    /* Scaled-fit mode (content-width/content-height): the inner .fit box
     * lays the content out at its authored fixed size and scales it onto
     * the printable area; .fit-box reserves the scaled footprint in flow
     * (transforms don't affect layout) and centers it. Without the mode,
     * both divs are unstyled block pass-throughs. */
    /* Explicit pagination: direct .page children are the pages. The sheet
     * becomes a transparent stack and each page carries the card look on
     * screen; at print each page is exactly one full-bleed sheet. The
     * ::slotted defaults are deliberately weak (document CSS wins), so
     * authored page styling can override any of this. */
    .sheet.paginated {
      background: transparent;
      box-shadow: none;
      border-radius: 0;
      padding: 0;
    }
    .paginated ::slotted(.page) {
      position: relative;
      display: block;
      width: 100%;
      aspect-ratio: var(--doc-page-ar);
      container-type: size;
      overflow: hidden;
      box-sizing: border-box;
      background: #fff;
      border-radius: 7px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
      print-color-adjust: exact;
      -webkit-print-color-adjust: exact;
      break-inside: avoid;
    }
    .paginated ::slotted(.page:not(:first-child)) { margin-top: 1rem; }
    @media print {
      .sheet.paginated { padding: 0; }
      /* The flowing-document vertical inset lives on the repeating
       * thead/tfoot spacers, not the sheet padding — they must go too,
       * or each full-sheet .page is pushed ~margin down and spills onto
       * a second sheet. Paginated pages are full-bleed by definition
       * (content owns its insets). */
      .sheet.paginated .hdr-space,
      .sheet.paginated .ftr-space { height: 0; }
      .paginated ::slotted(.page) {
        border-radius: 0 !important;
        box-shadow: none !important;
        margin: 0 !important;
        /* Physical page-box sizing, no viewport units: Safari resolves
         * 100vh against the window, not the page box, so a vh-sized card
         * paginates wrong there. --doc-page-w/h are the named size by
         * default and are overridden to the user's chosen paper by the
         * export path, so every card is exactly one sheet either way.
         * Width + height (same source values as @page size) rather than
         * width + aspect-ratio: the ratio is a 6-decimal rounding of the
         * same division, and a few millionths of overflow would spill a
         * blank sheet after every page. The screen-only aspect-ratio
         * (preview proportions) must not leak into print. cqh typography
         * tracks the same box.
         *
         * Every declaration is !important: per CSS Scoping, unimportant
         * shadow ::slotted rules LOSE to the document context, so a page
         * section's authored inline style would silently beat this print
         * geometry. A model-authored height:100% did exactly that — the
         * percentage resolves as auto in the all-auto print ancestry, the
         * base rule's size containment turns auto into ZERO, and
         * overflow:hidden then paints nothing: a blank PDF with perfect
         * page boxes. At print the component's geometry is the design's
         * whole contract, so it must win over any authored sizing. */
        aspect-ratio: auto !important;
        width: var(--doc-page-w) !important;
        height: var(--doc-page-h) !important;
        overflow: hidden !important;
      }
      .paginated ::slotted(.page:not(:first-child)) {
        break-before: page !important;
        margin-top: 0 !important;
      }
    }
    .fit-mode .fit-box {
      width: calc(var(--doc-fit-w) * var(--doc-fit-scale));
      height: calc(var(--doc-fit-h) * var(--doc-fit-scale));
      margin: 0 auto;
      break-inside: avoid;
    }
    /* Monolithic at print: Blink slices a transform-scaled child at
     * fragmentainer boundaries mapped in UNSCALED layout coordinates
     * (transforms are paint-time), so the .fit box (authored size, e.g.
     * 1400x990) gets cut at the page's free block space and spills onto
     * a second sheet even though its SCALED footprint fits the page by
     * construction. overflow:hidden makes .fit-box a scroll container —
     * monolithic under fragmentation (css-break-3) — so the scaled
     * content prints atomically on one sheet. No clipping for content
     * within the authored box: .fit-box is calc-sized to exactly the
     * scaled footprint. (Content that bleeds past content-width/height
     * is clipped at the footprint — fit mode's contract; it previously
     * painted beyond it at print.) Print-only, so the screen rendering
     * keeps visible overflow for editor affordances.
     * The export path injects the same rule into frozen copies
     * (print-eval.ts om-print-fit-contain). The .fit-mode scope is
     * load-bearing: .fit-box wraps slotted content in EVERY mode, and an
     * unscoped overflow:hidden would make whole flowing documents
     * monolithic (one truncated sheet). overflow:hidden, never clip —
     * clip is not a scroll container, so not monolithic. */
    @media print {
      .fit-mode .fit-box { overflow: hidden; }
    }
    .fit-mode .fit {
      width: var(--doc-fit-w);
      height: var(--doc-fit-h);
      transform: scale(var(--doc-fit-scale));
      transform-origin: top left;
    }
    .frame td, .frame th { padding: 0; text-align: left; font-weight: inherit; }
    .hdr-space { height: var(--doc-hdr-h); }
    .ftr-space { height: var(--doc-ftr-h); }
    ::slotted([slot="header"]),
    ::slotted([slot="footer"]) { display: block; box-sizing: border-box; }
    @media print {
      :host { background: none; padding: 0; min-width: 0; min-height: 0; }
      .sheet {
        width: auto; margin: 0; box-shadow: none; border-radius: 0;
        padding: 0 var(--doc-page-margin);
      }
      /* The thead/tfoot spacers repeat on every page, so they carry the
       * vertical page margin (which the sheet's own padding cannot, since
       * that padding is consumed once on the first/last page). The running
       * header/footer are fixed inside that band. */
      /* The 0.35in is breathing room between a running header/footer and
       * the body; without one the spacer is exactly the page margin, so a
       * margin="0" full-bleed document gets truly full-bleed pages. */
      .hdr-space { height: max(var(--doc-page-margin), calc(var(--doc-hdr-h) + var(--doc-hdr-pad))); }
      .ftr-space { height: max(var(--doc-page-margin), calc(var(--doc-ftr-h) + var(--doc-ftr-pad))); }
      /* WebKit flowing documents: @page carries the vertical margin (see
       * _syncPrintPageRule), so the spacers keep only whatever a running
       * header/footer needs BEYOND it — page 1 would otherwise double its
       * top inset. Paginated sheets already zero their spacers above. */
      .sheet.wk-print:not(.paginated) .hdr-space { height: max(0px, calc(max(var(--doc-page-margin), calc(var(--doc-hdr-h) + var(--doc-hdr-pad))) - var(--doc-page-margin))); }
      .sheet.wk-print:not(.paginated) .ftr-space { height: max(0px, calc(max(var(--doc-page-margin), calc(var(--doc-ftr-h) + var(--doc-ftr-pad))) - var(--doc-page-margin))); }
      ::slotted([slot="header"]) {
        position: fixed; top: 0; left: 0; right: 0; margin: 0;
        padding: calc(var(--doc-page-margin) * 0.45) var(--doc-page-margin) 0;
      }
      ::slotted([slot="footer"]) {
        position: fixed; bottom: 0; left: 0; right: 0; margin: 0;
        padding: 0 var(--doc-page-margin) calc(var(--doc-page-margin) * 0.45);
      }
    }
  `;
  class DocPage extends HTMLElement {
    static get observedAttributes() {
      return ['size', 'width', 'height', 'margin', 'orientation', 'content-width', 'content-height'];
    }
    constructor() {
      super();
      this._root = this.attachShadow({
        mode: 'open'
      });
      this._mo = typeof MutationObserver === 'function' ? new MutationObserver(() => this._scheduleMeasure()) : null;
    }

    /** The named paper's [w, h], swapped when orientation="landscape".
     *  Only the named size swaps — explicit width/height are exact values
     *  the author already oriented. */
    _paperSize() {
      const named = PAPER[(this.getAttribute('size') || '').toLowerCase()] || PAPER.letter;
      const landscape = (this.getAttribute('orientation') || '').trim().toLowerCase() === 'landscape';
      return landscape ? [named[1], named[0]] : named;
    }
    get pageWidth() {
      return safeLen(this.getAttribute('width'), this._paperSize()[0]);
    }
    get pageHeight() {
      return safeLen(this.getAttribute('height'), this._paperSize()[1]);
    }
    get pageMargin() {
      return safeLen(this.getAttribute('margin'), '0.75in');
    }

    /** Scaled-fit mode's content box [w, h] as CSS lengths, or null when
     *  the mode is off (either attribute missing/invalid/zero — a partial
     *  declaration falls back to normal flow rather than guessing). */
    _contentFit() {
      const w = safeLen(this.getAttribute('content-width'), null);
      const h = safeLen(this.getAttribute('content-height'), null);
      if (!w || !h) return null;
      const wPx = toPx(w),
        hPx = toPx(h);
      return wPx > 0 && hPx > 0 ? [w, h, wPx, hPx] : null;
    }
    connectedCallback() {
      if (!this._sheet) this._render();
      this._syncSize();
      this._syncPrintPageRule();
      this._ensureTextWrapDefaults();
      this._ensureOwnsPrintMeta();
      this._syncFixedSizeMeta();
      this._syncPrintSizingMeta();
      if (this._mo) this._mo.observe(this, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true
      });
      this._onResize = () => this._scheduleMeasure();
      window.addEventListener('resize', this._onResize);
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => this._scheduleMeasure());
      }
      this._scheduleMeasure();
    }
    disconnectedCallback() {
      window.removeEventListener('resize', this._onResize);
      if (this._mo) this._mo.disconnect();
      if (this._raf) {
        cancelAnimationFrame(this._raf);
        this._raf = null;
      }
      // Drop the head rules when the last doc-page leaves, so a deleted
      // document's @page geometry and text-wrap defaults can't apply to
      // whatever replaces it.
      const survivor = document.querySelector('doc-page');
      if (!survivor) {
        ['doc-page-print', 'doc-page-text-wrap', 'doc-page-owns-print', 'doc-page-fixed-size', 'doc-page-print-sizing'].forEach(id => {
          const tag = document.getElementById(id);
          if (tag) tag.remove();
        });
        // A live deck-stage deferred its own print-sizing meta to ours —
        // hand the page-global meta over so the deck isn't left unmarked.
        const deck = document.querySelector('deck-stage');
        if (deck && typeof deck._ensurePrintSizingMeta === 'function') {
          deck._ensurePrintSizingMeta();
        }
      } else {
        // A departed owner hands each page-global meta to whatever
        // doc-page remains (or it's removed).
        if (typeof survivor._syncFixedSizeMeta === 'function') {
          survivor._syncFixedSizeMeta();
        }
        if (typeof survivor._syncPrintSizingMeta === 'function') {
          survivor._syncPrintSizingMeta();
        }
      }
    }
    attributeChangedCallback() {
      if (!this._sheet) return;
      this._syncSize();
      this._syncPrintPageRule();
      this._syncFixedSizeMeta();
      this._syncPrintSizingMeta();
      this._scheduleMeasure();
    }
    _render() {
      this._root.innerHTML = `
        <style>${stylesheet}<\/style>
        <style id="vars"><\/style>
        <div class="sheet" data-screen-label="Document">
          <table class="frame" role="presentation">
            <thead><tr><th><div class="hdr-space"><slot name="header"><\/slot><\/div><\/th><\/tr><\/thead>
            <tbody><tr><td class="body"><div class="fit-box"><div class="fit"><slot><\/slot><\/div><\/div><\/td><\/tr><\/tbody>
            <tfoot><tr><td><div class="ftr-space"><slot name="footer"><\/slot><\/div><\/td><\/tr><\/tfoot>
          <\/table>
        <\/div>`;
      this._sheet = this._root.querySelector('.sheet');
      this._vars = this._root.getElementById('vars');
    }

    /** Runtime sizing lives in a shadow <style> :host rule, never on the
     *  light-DOM host element, so serialize-persist can't write it back. */
    _syncSize(hdrH, ftrH) {
      // Scaled-fit mode: content at its authored size, scaled onto the
      // printable area (page minus margins on both axes). The factor is a
      // plain number var so calc(length * number) stays valid; 4 decimals
      // keeps the shadow style stable across re-measures. Upscaling is
      // allowed — print transforms are vector, so text and CSS stay crisp
      // (raster images soften, which the catalog bullet warns about).
      const fit = this._contentFit();
      let fitVars = '';
      if (fit) {
        const marginPx = toPx(this.pageMargin) || 0;
        const availW = toPx(this.pageWidth) - 2 * marginPx;
        const availH = toPx(this.pageHeight) - 2 * marginPx;
        const scale = Math.min(availW / fit[2], availH / fit[3]);
        if (scale > 0 && Number.isFinite(scale)) {
          fitVars = '--doc-fit-w:' + fit[0] + ';' + '--doc-fit-h:' + fit[1] + ';' + '--doc-fit-scale:' + scale.toFixed(4) + ';';
        }
      }
      this._sheet.classList.toggle('fit-mode', !!fitVars);
      // Numeric w/h ratio for the paginated page cards' aspect-ratio —
      // aspect-ratio takes a number, not a length ratio, so compute it
      // here (CSS length division isn't portable). 6 decimals keeps the
      // shadow style stable across re-syncs.
      const arW = toPx(this.pageWidth);
      const arH = toPx(this.pageHeight);
      const ar = arW > 0 && arH > 0 ? (arW / arH).toFixed(6) : '0.772727';
      this._vars.textContent = ':host{' + fitVars + '--doc-page-ar:' + ar + ';' + '--doc-page-w:' + this.pageWidth + ';' + '--doc-page-h:' + this.pageHeight + ';' + '--doc-page-margin:' + this.pageMargin + ';' + '--doc-hdr-h:' + (hdrH || 0) + 'px;' + '--doc-ftr-h:' + (ftrH || 0) + 'px;' + '--doc-hdr-pad:' + (hdrH ? '0.35in' : '0px') + ';' + '--doc-ftr-pad:' + (ftrH ? '0.35in' : '0px') + '}';
    }

    /** @page is a no-op inside shadow DOM, so the rule lives in <head>.
     *  Re-appended on every sync so it stays last in source order — the
     *  @page cascade is source-order per descriptor, so this rule wins
     *  over any other @page rule in the document.
     *
     *  The @page SIZE is pinned where the page box IS part of the design:
     *  explicit-fixed-size mode (width + height authored), scaled-fit
     *  mode (the named sheet the fit targets), and explicit pagination
     *  (the named size the cards share — so card and sheet agree on
     *  every print path, and the export path's chosen paper overrides
     *  BOTH with one later rule). For FLOWING documents no paper size is
     *  emitted at all — the true size comes from the user's preference,
     *  injected by the export path or chosen in the print dialog — so a
     *  flowing document never fights the paper it lands on.
     *  margin: 0 is emitted in every mode: it leaves Chrome no margin box
     *  to draw its date/URL/page-count header in, and the visual margin
     *  lives on the sheet's own padding. */
    _syncPrintPageRule() {
      const id = 'doc-page-print';
      let tag = document.getElementById(id);
      if (!tag) {
        tag = document.createElement('style');
        tag.id = id;
      }
      document.head.appendChild(tag);
      // Three print-geometry regimes:
      // - true-size: the page IS the design — pin its exact size.
      // - scaled-fit (content-width/height): the fit factor is computed
      //   against the NAMED paper's printable area, so that paper must
      //   stay pinned or the scaled content overflows a smaller sheet
      //   (the export path re-fits and re-pins at print time on top).
      // - default modes: no paper size — but landscape still needs the
      //   paper-agnostic 'size: landscape' keyword, because the size
      //   descriptor is what carries orientation; without it a landscape
      //   document prints portrait whenever nothing injects a size.
      const landscape = (this.getAttribute('orientation') || '').trim().toLowerCase() === 'landscape';
      // Explicit pagination pins the page box to the SAME values that
      // size the cards (the named size by default, the export path's
      // chosen paper when its later rule overrides both) — card and
      // sheet agree on every print path, and a mismatched real paper
      // shrinks-to-fit in the dialog instead of clipping a Letter card
      // on A4. Declared before the paginated read below so both derive
      // from one check.
      const paginatedNow = this.querySelector(':scope > .page') !== null;
      const sizeDescriptor = this._trueSizePx() ? 'size: ' + this.pageWidth + ' ' + this.pageHeight + '; ' : this._contentFit() ? 'size: ' + this.pageWidth + ' ' + this.pageHeight + '; ' : paginatedNow ? 'size: ' + this.pageWidth + ' ' + this.pageHeight + '; ' : landscape ? 'size: landscape; ' : '';
      // WebKit never repeats the thead/tfoot spacers that carry a flowing
      // document's vertical page margins (see WK_PRINT above), so pages
      // after the first print edge-to-edge there. Carry the VERTICAL
      // margins on @page for WebKit instead, and the shadow print CSS
      // trims the first-page spacers by the same amount (.sheet.wk-print
      // rules). Horizontal inset stays on the sheet's own padding in
      // every engine. Blink keeps margin: 0 (a nonzero margin there
      // re-opens the box Chrome draws its header furniture in). One cost,
      // learned in testing: Safari's own date/URL headers are a USER
      // dialog setting ("Print headers and footers") that renders in the
      // margin area when room exists — margin: 0 only suppressed it by
      // leaving no room, and no CSS controls it. The export dialog's
      // Safari guide teaches turning the setting off for flowing
      // documents. Explicitly paginated and fixed-size documents keep
      // margin: 0 everywhere: their pages ARE the sheet.
      const wkFlowing = WK_PRINT && !paginatedNow && !this._trueSizePx() && !this._contentFit();
      const marginDescriptor = wkFlowing ? 'margin: ' + this.pageMargin + ' 0; ' : 'margin: 0; ';
      // Shadow-internal marker (never serialized), kept in lockstep with
      // the @page decision above: the print CSS trims the first-page
      // spacers ONLY while @page actually carries the margins — a
      // true-size or scaled-fit sheet keeps margin: 0 and must keep its
      // spacers too. Re-synced here so attribute changes and pagination
      // flips move both together.
      if (this._sheet) this._sheet.classList.toggle('wk-print', wkFlowing);
      tag.textContent = '@page { ' + sizeDescriptor + marginDescriptor + '} ' + '@media print { html, body { margin: 0 !important; padding: 0 !important; background: none !important; height: auto !important; overflow: visible !important; } ' + 'h1,h2,h3,h4,h5,h6 { break-after: avoid; } ' + 'figure,pre,blockquote,img,svg,tr { break-inside: avoid; } ' + 'p,li { orphans: 3; widows: 3; } ' + '* { -webkit-print-color-adjust: exact; print-color-adjust: exact; ' + 'backdrop-filter: none !important; -webkit-backdrop-filter: none !important; } ' + '*, *::before, *::after { animation-delay: -99s !important; animation-duration: .001s !important; ' + 'animation-iteration-count: 1 !important; animation-fill-mode: both !important; ' + 'animation-play-state: running !important; transition-duration: 0s !important; } }';
    }

    /** Typographic defaults for document text: balance headings, avoid
     *  widowed/orphaned words in body copy (browsers without text-wrap
     *  support drop the declarations). Zero-specificity via :where() so
     *  any text-wrap authored on those elements wins; document-level so the
     *  rules reach the slotted (light DOM) content — shadow styles can't.
     *  data-omelette-injected marks the tag for the host editor to strip
     *  at serialize, so it is never written back as authored source. */
    _ensureTextWrapDefaults() {
      if (document.getElementById('doc-page-text-wrap')) return;
      const tag = document.createElement('style');
      tag.id = 'doc-page-text-wrap';
      tag.setAttribute('data-omelette-injected', '');
      tag.textContent = ':where(h1,h2,h3,h4,h5,h6){text-wrap:balance}' + ':where(p,li,blockquote,figcaption){text-wrap:pretty}';
      document.head.appendChild(tag);
    }

    /** Declares that this document owns its print CSS. The instant-PDF
     *  export checks for the meta by NAME PRESENCE alone (content is
     *  ignored) and skips its automatic print-CSS injections, so the
     *  component's @page geometry is never overridden by a heuristic.
     *  data-omelette-injected keeps it out of serialized source. */
    _ensureOwnsPrintMeta() {
      if (document.getElementById('doc-page-owns-print')) return;
      const tag = document.createElement('meta');
      tag.id = 'doc-page-owns-print';
      tag.name = 'omelette-owns-print';
      tag.content = 'true';
      tag.setAttribute('data-omelette-injected', '');
      document.head.appendChild(tag);
    }

    /** This page's valid true-size page box (explicit width AND height)
     *  as [w, h] px ints, or null when the mode is off. */
    _trueSizePx() {
      if (!safeLen(this.getAttribute('width'), null) || !safeLen(this.getAttribute('height'), null)) return null;
      const w = Math.round(toPx(this.pageWidth));
      const h = Math.round(toPx(this.pageHeight));
      return w > 0 && h > 0 ? [w, h] : null;
    }

    /** True-size pages (explicit width AND height) also declare the page
     *  box as the preview size: the in-app preview reads
     *  meta[name="omelette-fixed-size"] (content "W,H" in px ints) and
     *  scales the sheet into view — without it an 18in poster previews at
     *  true size with scrollbars. Never overrides an author-set meta
     *  (only the component's own id is managed). The meta is page-global
     *  while doc-page instances are not, so every sync recomputes the
     *  page-wide owner — the first connected true-size doc-page — and a
     *  non-true-size sibling's sync can never delete the owner's meta.
     *  Removed when no true-size page remains (the owner's disconnect
     *  re-syncs via any survivor) or when an author-set meta exists. */
    _syncFixedSizeMeta() {
      const id = 'doc-page-fixed-size';
      const own = document.getElementById(id);
      const authored = document.querySelector('meta[name="omelette-fixed-size"]:not([data-omelette-injected])');
      // The page-wide owner, not this instance: an upgraded true-size page
      // anywhere in the document keeps the meta alive and sized.
      let box = null;
      for (const el of document.querySelectorAll('doc-page')) {
        box = typeof el._trueSizePx === 'function' ? el._trueSizePx() : null;
        if (box) break;
      }
      if (!box || authored) {
        if (own) own.remove();
        return;
      }
      const tag = own || document.createElement('meta');
      tag.id = id;
      tag.name = 'omelette-fixed-size';
      tag.content = box[0] + ',' + box[1];
      tag.setAttribute('data-omelette-injected', '');
      if (!own) document.head.appendChild(tag);
    }

    /** This page's print-sizing mode: 'fixed' when an explicit width AND
     *  height are authored (the page is the design's own size), else the
     *  default paper in the authored orientation. */
    _printSizingMode() {
      if (this._trueSizePx()) return 'fixed';
      const landscape = (this.getAttribute('orientation') || '').trim().toLowerCase() === 'landscape';
      return landscape ? 'default-landscape' : 'default-portrait';
    }

    /** Announces the print-sizing mode to the host app:
     *  meta[name="omelette-print-sizing"] with content 'default-portrait',
     *  'default-landscape', or 'fixed' (fixed pages also carry the
     *  omelette-fixed-size meta with the page box in px). The export path
     *  probes it to decide what true paper size to inject at print time —
     *  in the default modes the component emits no paper size of its own.
     *  Same page-global ownership rules as the fixed-size meta above:
     *  first connected doc-page owns it, an authored meta is never
     *  overridden, removed when no doc-page remains. */
    _syncPrintSizingMeta() {
      const id = 'doc-page-print-sizing';
      const own = document.getElementById(id);
      const authored = document.querySelector('meta[name="omelette-print-sizing"]:not([data-omelette-injected])');
      // A fixed page wins outright (mirroring the fixed-size loop above,
      // so the two metas can never contradict each other in a mixed
      // multi-page document); otherwise the first page's mode holds.
      let mode = null;
      for (const el of document.querySelectorAll('doc-page')) {
        if (typeof el._printSizingMode !== 'function') continue;
        const m = el._printSizingMode();
        if (m === 'fixed') {
          mode = m;
          break;
        }
        if (mode === null) mode = m;
      }
      if (!mode || authored) {
        if (own) own.remove();
        return;
      }
      // A deck-stage that connected first injected its own meta and
      // defers to any existing one — take it over, or the document ends
      // up with two conflicting injected metas (a doc-page page is the
      // document; the deck re-ensures its meta if every doc-page leaves).
      const deckMeta = document.getElementById('deck-stage-print-sizing');
      if (deckMeta) deckMeta.remove();
      const tag = own || document.createElement('meta');
      tag.id = id;
      tag.name = 'omelette-print-sizing';
      tag.content = mode;
      tag.setAttribute('data-omelette-injected', '');
      if (!own) document.head.appendChild(tag);
    }
    _scheduleMeasure() {
      if (this._raf) return;
      this._raf = requestAnimationFrame(() => {
        this._raf = null;
        this._measure();
      });
    }

    /** Slot heights feed the print spacers (--doc-hdr-h / --doc-ftr-h), so
     *  they re-measure on content mutation, resize, and font load. The
     *  same pass detects explicit pagination (direct .page children) and
     *  toggles the sheet between the flowing-document card and the
     *  page-per-card stack — content edits can add or remove pages at any
     *  time, so this tracks the same mutations the measurement does. */
    _measure() {
      const hdr = this.querySelector(':scope > [slot="header"]');
      const ftr = this.querySelector(':scope > [slot="footer"]');
      const wasPaginated = this._sheet.classList.contains('paginated');
      this._sheet.classList.toggle('paginated', this.querySelector(':scope > .page') !== null);
      // The WebKit @page margin is flowing-only, so a pagination flip
      // must re-emit the rule (content edits can add or remove .page
      // sections at any time).
      if (this._sheet.classList.contains('paginated') !== wasPaginated) {
        this._syncPrintPageRule();
      }
      this._syncSize(hdr ? hdr.offsetHeight : 0, ftr ? ftr.offsetHeight : 0);
    }
  }
  if (!customElements.get('doc-page')) {
    customElements.define('doc-page', DocPage);
  }
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/game/doc-page.js", error: String((e && e.message) || e) }); }

// ui_kits/site/SitePage.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  NavBar,
  Image: DSImage,
  ProgressBar,
  BoxContainer
} = window.PyguaraDesignSystem_ca79d7;
const A = '../../assets/';
const wrap = {
  maxWidth: 1080,
  margin: '0 auto',
  padding: '0 24px'
};
const H2 = ({
  t,
  k
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    marginBottom: 22
  }
}, k && /*#__PURE__*/React.createElement("div", {
  style: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    letterSpacing: 'var(--ls-caps)',
    textTransform: 'uppercase',
    color: 'var(--action-secondary)',
    marginBottom: 9
  }
}, k), /*#__PURE__*/React.createElement("h2", {
  style: {
    margin: 0,
    fontFamily: 'var(--font-pixel)',
    fontSize: 'clamp(22px,3.4vw,32px)',
    letterSpacing: 'var(--ls-pixel)',
    color: 'var(--text-heading)',
    textWrap: 'pretty'
  }
}, t));
function SiteApp() {
  const [wish, setWish] = React.useState(false);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(NavBar, {
    height: 62,
    align: "STRETCH",
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 30,
      padding: '0 24px',
      background: 'var(--surface-overlay)',
      backdropFilter: 'blur(6px)'
    },
    brand: /*#__PURE__*/React.createElement("img", {
      src: A + 'art/logo-pyguara-lockup.png',
      alt: "Guar\xE1 & Falc\xE3o",
      style: {
        height: 38
      }
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "The World",
    variant: "ghost",
    size: "small"
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Engine",
    variant: "ghost",
    size: "small"
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Devlog",
    variant: "ghost",
    size: "small"
  }), /*#__PURE__*/React.createElement(Button, {
    text: wish ? 'Wishlisted' : 'Wishlist',
    size: "small",
    onClick: () => setWish(w => !w)
  }))), /*#__PURE__*/React.createElement("header", {
    style: {
      position: 'relative',
      overflow: 'hidden',
      borderBottom: '2px solid var(--edge-strong)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/scene-window-grove.png',
    alt: "",
    style: {
      position: 'absolute',
      inset: 0,
      width: '100%',
      height: '100%',
      objectFit: 'cover'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      background: 'linear-gradient(180deg,rgba(29,22,32,.5),rgba(29,22,32,.92))'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      ...wrap,
      position: 'relative',
      padding: '86px 24px 96px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 600
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/logo-pyguara-lockup.png',
    alt: "Pyguara Solar Engine \u2014 Guar\xE1 & Falc\xE3o",
    style: {
      width: 'min(420px,100%)'
    }
  }), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 20,
      lineHeight: 'var(--lh-body)',
      color: 'var(--sand-100)',
      margin: '22px 0 0',
      textWrap: 'pretty'
    }
  }, "A maned wolf runs the Brazilian Cerrado. A falcon rides on his back. The platforms are solar, the water is piped, and someone keeps all of it running."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 12,
      marginTop: 28
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: wish ? 'On your wishlist' : 'Wishlist',
    variant: "sage",
    size: "large",
    onClick: () => setWish(w => !w)
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Watch the trailer",
    variant: "wood",
    size: "large"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 20,
      marginTop: 24,
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--sand-200)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "Windows \xB7 macOS \xB7 Linux"), /*#__PURE__*/React.createElement("span", null, "Single player"), /*#__PURE__*/React.createElement("span", null, "2027"))))), /*#__PURE__*/React.createElement("section", {
    style: {
      ...wrap,
      padding: '72px 24px'
    }
  }, /*#__PURE__*/React.createElement(H2, {
    k: "Two animals, one run",
    t: "Guar\xE1 runs. Falc\xE3o carries."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))',
      gap: 20
    }
  }, [[A + 'art/hero-guara.png', 'Guará', 'Heavy, fast, committed. He cannot double-jump — momentum is the whole puzzle.'], [A + 'art/sprite-falcao.png', 'Falcão', 'Three charges. Spend one to hover, glide a gap, or scout what the camera will not show you.'], [A + 'art/prop-solar-leaf-panel.png', 'The engine below', 'Every roça platform runs on solar leaf and piped water. Stall one and the level changes shape.']].map(([src, t, d]) => /*#__PURE__*/React.createElement(Panel, {
    key: t,
    borderWidth: 2,
    padding: "0",
    style: {
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: 148,
      display: 'grid',
      placeItems: 'center',
      background: 'var(--surface-inset)',
      borderBottom: '1px solid var(--edge)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: "",
    style: {
      maxHeight: 112,
      maxWidth: '80%'
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '16px 18px'
    }
  }, /*#__PURE__*/React.createElement(Label, {
    text: t,
    font: "pixel",
    fontSize: 16,
    color: "var(--text-heading)"
  }), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '9px 0 0',
      fontSize: 15,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-muted)',
      textWrap: 'pretty'
    }
  }, d)))))), /*#__PURE__*/React.createElement("section", {
    style: {
      background: 'var(--surface-card)',
      borderTop: '1px solid var(--edge)',
      borderBottom: '1px solid var(--edge)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...wrap,
      padding: '64px 24px',
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))',
      gap: 36,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(H2, {
    k: "Built in the open",
    t: "Runs on Pyguara, our own engine"
  }), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 17,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-muted)',
      margin: 0,
      maxWidth: '52ch',
      textWrap: 'pretty'
    }
  }, "Pyguara is a data-driven, event-driven 2D engine on pygame and pymunk. Entities are component compositions; systems query them each frame. It ships an ECS, a physics layer, a scene serializer, hot reload, and an in-game editor. It is open source."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      marginTop: 24
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Read the docs",
    variant: "secondary"
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Source on GitHub",
    variant: "ghost"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      placeItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/badge-pyguara-mark.png',
    alt: "Pyguara Engine",
    style: {
      width: 'min(230px,70%)'
    }
  })))), /*#__PURE__*/React.createElement("section", {
    style: {
      ...wrap,
      padding: '72px 24px'
    }
  }, /*#__PURE__*/React.createElement(H2, {
    k: "Progress",
    t: "What is done"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))',
      gap: 18
    }
  }, [['Cerrado biome', 1], ['Guará moveset', .9], ['Falcão flight', .65], ['Roça machinery', .4], ['Soundtrack', .25]].map(([t, v]) => /*#__PURE__*/React.createElement(Panel, {
    key: t,
    padding: "14px 16px"
  }, /*#__PURE__*/React.createElement(Label, {
    text: t,
    fontSize: 13,
    color: "var(--text-body)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement(ProgressBar, {
    value: v,
    width: 0,
    style: {
      width: '100%'
    },
    label: Math.round(v * 100) + '%'
  })))))), /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: '2px solid var(--edge-strong)',
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...wrap,
      padding: '34px 24px',
      display: 'flex',
      flexWrap: 'wrap',
      gap: 18,
      alignItems: 'center',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/badge-pyguara-mark.png',
    alt: "Pyguara Engine",
    style: {
      height: 44
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 18,
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#docs"
  }, "Docs"), /*#__PURE__*/React.createElement("a", {
    href: "#press"
  }, "Press kit"), /*#__PURE__*/React.createElement("a", {
    href: "#devlog"
  }, "Devlog"), /*#__PURE__*/React.createElement("a", {
    href: "#contact"
  }, "Contact")))));
}
Object.assign(window, {
  SiteApp
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/site/SitePage.jsx", error: String((e && e.message) || e) }); }

// ui_kits/store/StorePage.jsx
try { (() => {
const {
  Panel,
  Label,
  Button,
  NavBar,
  Image: DSImage,
  ProgressBar,
  Checkbox
} = window.PyguaraDesignSystem_ca79d7;
const A = '../../assets/';
const SHOTS = [A + 'art/scene-cerrado-solar.png', A + 'art/tiles-plank-platform.png', A + 'art/props-trees.png', A + 'art/prop-solar-leaf-panel.png'];
function StoreApp() {
  const [shot, setShot] = React.useState(0);
  const [follow, setFollow] = React.useState(false);
  const [tip, setTip] = React.useState('5');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1000,
      margin: '0 auto',
      padding: '0 20px 80px'
    }
  }, /*#__PURE__*/React.createElement(NavBar, {
    height: 54,
    align: "STRETCH",
    style: {
      padding: '0 4px',
      background: 'transparent',
      borderBottom: '1px solid var(--edge)'
    },
    brand: /*#__PURE__*/React.createElement(Label, {
      text: "GUAR\xC1 & FALC\xC3O",
      font: "display",
      fontSize: 12,
      color: "var(--text-heading)"
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: follow ? 'Following' : 'Follow',
    variant: "ghost",
    size: "small",
    onClick: () => setFollow(v => !v)
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Share",
    variant: "ghost",
    size: "small"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))',
      gap: 26,
      marginTop: 26,
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "0",
    style: {
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: SHOTS[shot],
    alt: "Screenshot",
    style: {
      display: 'block',
      width: '100%',
      height: 300,
      objectFit: 'cover'
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      marginTop: 8,
      overflowX: 'auto',
      paddingBottom: 4
    }
  }, SHOTS.map((s, i) => /*#__PURE__*/React.createElement("button", {
    key: s,
    type: "button",
    onClick: () => setShot(i),
    style: {
      flex: '0 0 auto',
      padding: 0,
      width: 96,
      height: 60,
      overflow: 'hidden',
      cursor: 'pointer',
      border: '2px solid ' + (i === shot ? 'var(--action-secondary)' : 'var(--edge)'),
      background: 'var(--surface-inset)'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: s,
    alt: "",
    style: {
      width: '100%',
      height: '100%',
      objectFit: 'cover',
      display: 'block'
    }
  })))), /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: '28px 0 0',
      fontFamily: 'var(--font-pixel)',
      fontSize: 'clamp(22px,3.6vw,30px)',
      letterSpacing: 'var(--ls-pixel)',
      color: 'var(--text-heading)'
    }
  }, "Guar\xE1 & Falc\xE3o"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '6px 0 0',
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-faint)'
    }
  }, "A platformer adventure \xB7 by Wedeueis \xB7 devlog 14"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 17,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-body)',
      maxWidth: '64ch',
      marginTop: 22,
      textWrap: 'pretty'
    }
  }, "A maned wolf runs the Brazilian Cerrado at dusk. A falcon rides on his back and spends himself three times before he has to land. Beneath the tableland, old machinery is still turning \u2014 greened over and kept running, and the platforms you need are the parts still in motion."), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 17,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-muted)',
      maxWidth: '64ch',
      textWrap: 'pretty'
    }
  }, "Momentum is the whole puzzle. Guar\xE1 cannot double-jump. Falc\xE3o can carry you across one gap, not two. Stalling a gear changes the level's shape, and you have to want that."), /*#__PURE__*/React.createElement("h2", {
    style: {
      marginTop: 34,
      fontFamily: 'var(--font-pixel)',
      fontSize: 17,
      letterSpacing: 'var(--ls-pixel)',
      color: 'var(--text-heading)'
    }
  }, "Features"), /*#__PURE__*/React.createElement("ul", {
    style: {
      margin: '12px 0 0',
      padding: 0,
      listStyle: 'none',
      display: 'grid',
      gap: 8
    }
  }, ['Hand-animated pixel art at 12 fps — every frame drawn, none tweened', 'One biome, studied properly: the Cerrado in three seasons', 'Machinery you can stall, reverse or ride', 'Open-source engine — the editor ships with the game'].map(t => /*#__PURE__*/React.createElement("li", {
    key: t,
    style: {
      display: 'flex',
      gap: 10,
      fontSize: 16,
      lineHeight: 'var(--lh-body)',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--action-secondary)',
      flex: '0 0 auto'
    }
  }, "\u25AA"), t)))), /*#__PURE__*/React.createElement("aside", {
    style: {
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 16,
      position: 'sticky',
      top: 16
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    borderWidth: 2,
    padding: "18px"
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Name your own price",
    fontSize: 12,
    color: "var(--text-muted)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 6,
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-pixel)',
      fontSize: 26,
      color: 'var(--text-heading)'
    }
  }, "$12"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-faint)'
    }
  }, "suggested")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6,
      marginTop: 14
    }
  }, ['5', '12', '25'].map(v => /*#__PURE__*/React.createElement(Button, {
    key: v,
    text: '$' + v,
    size: "small",
    variant: tip === v ? 'primary' : 'ghost',
    onClick: () => setTip(v),
    style: {
      minWidth: 52
    }
  }))), /*#__PURE__*/React.createElement(Button, {
    text: "Buy now",
    variant: "sage",
    size: "large",
    fullWidth: true,
    style: {
      marginTop: 14
    }
  }), /*#__PURE__*/React.createElement(Button, {
    text: "Download demo",
    variant: "wood",
    fullWidth: true,
    style: {
      marginTop: 8
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      lineHeight: 1.7
    }
  }, "Windows \xB7 macOS \xB7 Linux", /*#__PURE__*/React.createElement("br", null), "1.4 GB \xB7 DRM-free")), /*#__PURE__*/React.createElement(Panel, {
    padding: "16px"
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Development",
    fontSize: 12,
    color: "var(--text-muted)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, [['Chapter 1', 1], ['Chapter 2', .55], ['Chapter 3', .1]].map(([t, v]) => /*#__PURE__*/React.createElement("div", {
    key: t
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginBottom: 4
    }
  }, t), /*#__PURE__*/React.createElement(ProgressBar, {
    value: v,
    width: 0,
    style: {
      width: '100%'
    }
  }))))), /*#__PURE__*/React.createElement(Panel, {
    padding: "16px"
  }, /*#__PURE__*/React.createElement(Label, {
    text: "Details",
    fontSize: 12,
    color: "var(--text-muted)"
  }), /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      marginTop: 10,
      fontFamily: 'var(--font-mono)',
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("tbody", null, [['Status', 'In development'], ['Genre', 'Platformer'], ['Engine', 'Pyguara'], ['Tags', 'pixel-art, cerrado'], ['Languages', 'pt-BR, en'], ['Input', 'Keyboard, gamepad']].map(([k, v]) => /*#__PURE__*/React.createElement("tr", {
    key: k
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '5px 0',
      color: 'var(--text-faint)',
      verticalAlign: 'top'
    }
  }, k), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '5px 0 5px 12px',
      color: 'var(--text-body)'
    }
  }, v)))))), /*#__PURE__*/React.createElement(Panel, {
    padding: "16px"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: A + 'art/badge-pyguara-mark.png',
    alt: "Pyguara Engine",
    style: {
      height: 52
    }
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Label, {
    text: "Made with Pyguara",
    fontSize: 12,
    color: "var(--text-body)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement(Button, {
    text: "Get the engine",
    variant: "ghost",
    size: "small",
    style: {
      fontSize: 11
    }
  }))))))));
}
Object.assign(window, {
  StoreApp
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/store/StorePage.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Canvas = __ds_scope.Canvas;

__ds_ns.Image = __ds_scope.Image;

__ds_ns.Label = __ds_scope.Label;

__ds_ns.Panel = __ds_scope.Panel;

__ds_ns.ProgressBar = __ds_scope.ProgressBar;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Slider = __ds_scope.Slider;

__ds_ns.TextInput = __ds_scope.TextInput;

__ds_ns.BoxContainer = __ds_scope.BoxContainer;

__ds_ns.NavBar = __ds_scope.NavBar;

})();
