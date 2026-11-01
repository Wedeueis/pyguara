import React from 'react';

/* Mirrors pyguara/ui/components/image.py — draws a texture into a rect,
   optionally tinted. Pixel art must never be smoothed on upscale. */
export function Image({src,alt='',width,height,tint,pixelated=true,style,...rest}){
  const img=<img src={src} alt={alt} width={width} height={height} style={{
    display:'block',width:width?width+'px':'100%',height:height?height+'px':'auto',
    imageRendering:pixelated?'pixelated':'auto',...(tint?{}:style),
  }} {...(tint?{}:rest)} />;
  if(!tint) return img;
  return <span style={{position:'relative',display:'inline-block',...style}} {...rest}>
    {img}
    <span aria-hidden="true" style={{position:'absolute',inset:0,background:tint,mixBlendMode:'multiply',pointerEvents:'none'}} />
  <\/span>;
}
