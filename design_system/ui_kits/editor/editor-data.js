window.EditorData={
entities:[
 {id:'0a3f91c2',tag:'guara_player',src:'res://prefabs/guara_player.json',comps:{
   Transform:{position:'(320.0, 448.0)',rotation:'0.0',scale:'(1.0, 1.0)'},
   RigidBody:{mass:'12.0',body_type:'DYNAMIC',friction:'0.85',gravity_scale:'1.0'},
   Collider:{shape:'BOX',size:'(28.0, 40.0)',offset:'(0.0, -4.0)',is_sensor:'False'},
   Sprite:{texture:'guara_atlas',layer:'10',flip_x:'False',tint:'(255, 255, 255, 255)'},
   Animation:{clip:'idle',fps:'12',loop:'True'},
   PlatformerController:{move_speed:'240.0',jump_force:'560.0',coyote_time:'0.12'}}},
 {id:'6c1d40ab',tag:'falcao_companion',src:'res://prefabs/falcao.json',comps:{
   Transform:{position:'(356.0, 402.0)',rotation:'0.0',scale:'(1.0, 1.0)'},
   Sprite:{texture:'falcao_atlas',layer:'11',flip_x:'False',tint:'(255, 255, 255, 255)'},
   Animation:{clip:'hover',fps:'12',loop:'True'},
   SteeringAgent:{behavior:'FOLLOW',max_speed:'300.0',arrive_radius:'48.0'}}},
 {id:'b208ee71',tag:'roca_platform_03',src:'res://levels/roca_01.json',comps:{
   Transform:{position:'(704.0, 512.0)',rotation:'0.0',scale:'(2.0, 1.0)'},
   RigidBody:{mass:'0.0',body_type:'STATIC',friction:'1.0',gravity_scale:'0.0'},
   Collider:{shape:'BOX',size:'(128.0, 32.0)',offset:'(0.0, 0.0)',is_sensor:'False'}}},
 {id:'ff40a9d5',tag:'gear_hazard_01',comps:{
   Transform:{position:'(928.0, 480.0)',rotation:'14.0',scale:'(1.0, 1.0)'},
   Collider:{shape:'CIRCLE',size:'(20.0, 20.0)',offset:'(0.0, 0.0)',is_sensor:'True'},
   TriggerVolume:{on_enter:'damage_player',once:'False'}}},
 {id:'3e77b104',tag:'fruit_pickup_07',comps:{
   Transform:{position:'(512.0, 416.0)',rotation:'0.0',scale:'(1.0, 1.0)'},
   Sprite:{texture:'items_atlas',layer:'8',flip_x:'False',tint:'(255, 255, 255, 255)'},
   TriggerVolume:{on_enter:'collect_fruit',once:'True'}}},
 {id:'91ba2cf0',tag:'main_camera',comps:{
   Transform:{position:'(320.0, 448.0)',rotation:'0.0',scale:'(1.0, 1.0)'},
   Camera:{zoom:'2.0',follow_target:'guara_player',deadzone:'(48.0, 32.0)'}}},
 {id:'c40d18e3',comps:{Transform:{position:'(0.0, 0.0)',rotation:'0.0',scale:'(1.0, 1.0)'},AmbientLight:{color:'(255, 214, 150, 255)',intensity:'0.85'}}}
],
registry:['guara_player.json -> res://prefabs/guara_player.json','falcao.json -> res://prefabs/falcao.json','roca_01.json -> res://levels/roca_01.json','cerrado_ground.tsx -> res://tiles/cerrado_ground.tsx','theme_cerrado.json -> res://ui/theme_cerrado.json'],
cache:[['DataResource','guara_player.json','res://prefabs/guara_player.json'],['DataResource','roca_01.json','res://levels/roca_01.json'],['TextureResource','guara_atlas.png','res://atlas/guara_atlas.png'],['TextureResource','cerrado_tiles.png','res://atlas/cerrado_tiles.png'],['AudioResource','wind_loop.ogg','res://audio/wind_loop.ogg'],['DataResource','theme_cerrado.json','res://ui/theme_cerrado.json']],
shortcuts:[['F1','Performance Monitor'],['F2','Entity Inspector'],['F3','Event Monitor'],['F4','Physics Debugger'],['F5','Robust ImGui Editor'],['F8','Shortcuts Panel (This)'],['F12','Toggle ALL Tools']],
events:[['12.481','PhysicsStepEvent','dt=0.0167'],['12.483','CollisionEnterEvent','guara_player ↔ roca_platform_03'],['12.501','AnimationClipChanged','guara_player: idle → run'],['12.540','TriggerEnterEvent','fruit_pickup_07'],['12.541','ResourceLoaded','res://audio/pickup.ogg'],['12.612','InputActionEvent','jump (pressed)'],['12.613','PlatformerJumpEvent','force=560.0']]
};