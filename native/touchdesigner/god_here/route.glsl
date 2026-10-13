uniform float uTime;
uniform vec4 uRoute;
uniform vec4 uAddress;
uniform vec4 uValid;
out vec4 fragColor;
void main(){
 vec2 uv=vec2(vUV.x,1-vUV.y); float phase=mod(max(0,uTime)/max(.08,uRoute.x),2.0); float progress=phase<1?phase:2-phase; int count=int(uRoute.y+.5);vec4 result=vec4(0);
 for(int j=3;j>=0;j--){if(j>=count||uValid[j]<.5)continue;float q=clamp(progress-float(j)*.12*uRoute.z,0,1);float x=mix(uAddress.x,uAddress.y,q);vec2 p=(uv-vec2(x-.31,.19-sin(q*3.14159265)*.3))/.62;
 if(all(greaterThanEqual(p,vec2(0)))&&all(lessThanEqual(p,vec2(1)))){vec4 src=texture(sTD2DInputs[nonuniformEXT(j)],vec2(p.x,1-p.y))*(1-float(j)/float(count+1))*.95;result=src+result*(1-src.a);}}
 fragColor=TDOutputSwizzle(result);}
