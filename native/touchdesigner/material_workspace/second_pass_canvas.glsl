// Five source-aware fields, one temporal trace, expressive words, captions, reference.
uniform vec4 uAnchor;
uniform vec4 uField0; uniform vec4 uField1; uniform vec4 uField2;
uniform vec4 uField3; uniform vec4 uField4; uniform vec4 uField5;
uniform vec4 uCrop0; uniform vec4 uCrop1; uniform vec4 uCrop2;
uniform vec4 uCrop3; uniform vec4 uCrop4; uniform vec4 uCrop5;
uniform vec4 uLevels0; uniform vec4 uLevels1; uniform vec4 uWords;
out vec4 fragColor;
vec4 sampleField(int i,vec2 p){
    if(i==0)return texture(sTD2DInputs[0],p);
    if(i==1)return texture(sTD2DInputs[1],p);
    if(i==2)return texture(sTD2DInputs[2],p);
    if(i==3)return texture(sTD2DInputs[3],p);
    if(i==4)return texture(sTD2DInputs[4],p);
    return texture(sTD2DInputs[5],p);
}
vec4 layer(int i,vec2 uv,vec4 r,vec4 crop,float gain){
    vec2 q=(uv-r.xy)/max(r.zw,vec2(.001))+.5;
    if(any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1))))return vec4(0);
    return sampleField(i,crop.xy+q*crop.zw)*gain;
}
vec4 over(vec4 a,vec4 b){return a+b*(1.-a.a);}
void main(){
    vec2 uv=vUV.st;
    vec4 color=vec4(.018,.021,.026,1);
    color=over(layer(0,uv,uField0,uCrop0,uLevels0.x),color);
    color=over(layer(1,uv,uField1,uCrop1,uLevels0.y),color);
    color=over(layer(2,uv,uField2,uCrop2,uLevels0.z),color);
    color=over(layer(3,uv,uField3,uCrop3,uLevels0.w),color);
    color=over(layer(4,uv,uField4,uCrop4,uLevels1.x),color);
    color=over(layer(5,uv,uField5,uCrop5,uLevels1.y),color);
    vec2 wordUV=(uv-uWords.xy)/max(uWords.zw,vec2(.001))+.5;
    if(all(greaterThanEqual(wordUV,vec2(0)))&&all(lessThanEqual(wordUV,vec2(1))))
        color=over(texture(sTD2DInputs[6],wordUV)*uLevels1.z,color);
    if(uv.y<.15)color=over(texture(sTD2DInputs[7],vec2(uv.x,uv.y/.15)),color);
    vec2 q=(uv-uAnchor.xy)/uAnchor.zw+.5;
    if(all(greaterThanEqual(q,vec2(0)))&&all(lessThanEqual(q,vec2(1))))
        color=texture(sTD2DInputs[8],q);
    fragColor=TDOutputSwizzle(color);
}
