uniform float uPortrait;
out vec4 fragColor;
vec4 Panel(vec2 uv,vec4 r,int image){
 vec2 p=(uv-r.xy)/r.zw;
 if(any(lessThan(p,vec2(0)))||any(greaterThan(p,vec2(1))))return vec4(0);
 return texture(sTD2DInputs[nonuniformEXT(image)],p);
}
void main(){
 vec2 uv=vUV.st;vec4 c=vec4(.018,.022,.029,1);
 // Two 16:9 panels: untreated anchor above, selected result below, no overlaps.
 vec4 ref=uPortrait>.5?vec4(.04,.65,.92,.29109375):vec4(.04,.28,.44,.44);
 vec4 wet=uPortrait>.5?vec4(.04,.29,.92,.29109375):vec4(.52,.28,.44,.44);
 vec4 a=Panel(uv,ref,0),b=Panel(uv,wet,1);
 if(a.a>0)c=a;if(b.a>0)c=b;
 fragColor=TDOutputSwizzle(c);
}
