// Native translation of web/fx/visual-engine.mjs, Message impact only.
// Inputs: untreated source; 20 timestamped source-history taps; OUT/HOW/WHAT glyphs.
uniform float uTime;
uniform float uWet;
uniform vec4 uRoute; // travel,copies,spread,arrival
uniform vec4 uAddress; // origin,destination
uniform vec4 uEcho; // time,taps,decay,spread
uniform float uEchoScale;
uniform vec4 uField; // amount,scale,speed,spill
uniform vec4 uRegion;
uniform vec4 uType; // size,copies,persistence,fragment
uniform float uDrift;
uniform vec4 uValid0, uValid1, uValid2, uValid3, uValid4;
out vec4 fragColor;
vec4 Over(vec4 a, vec4 b) { return a + b*(1.0-a.a); }
bool Inside(vec2 p) { return all(greaterThanEqual(p,vec2(0))) && all(lessThanEqual(p,vec2(1))); }
float Valid(int k,int j) {
    if(k==1)return uValid0[j];if(k==2)return uValid1[j];if(k==3)return uValid2[j];if(k==4)return uValid3[j];return uValid4[j];
}
vec4 Glyph(vec2 p,float t) {
    if(!Inside(p))return vec4(0);
    // Same provisional anchors/persistence as existing cue bank; no certified captions.
    int id=0; float end=3.12;
    if(t>=5.1)end=5.42;if(t>=5.6)end=5.68;
    if(t>=6.14){id=1;end=6.52;}if(t>=8.06){id=1;end=8.34;}
    if(t>=9.94){id=2;end=10.08;}
    if(t-end>uType.z)return vec4(0);
    return texture(sTD2DInputs[nonuniformEXT(6+id)],vec2(p.x,1-p.y));
}
float SeedNoise(int i){uint n=1427u^((uint(i)+1u)*374761393u)^668265263u;n=(n^(n>>13))*1274126177u;return float(n^(n>>16))/4294967296.0;}
vec4 Routed(vec2 uv,float t,int tap,bool words) {
    if(!words) { if(!Inside(uv))return vec4(0); return texture(sTD2DInputs[nonuniformEXT(tap)],vec2(uv.x,1-uv.y)); }
    float phase=mod(max(0,t)/max(.08,uRoute.x),2.0);
    float progress=phase<1.0?phase:2.0-phase;
    int count=int(uRoute.y+.5);vec4 result=vec4(0);
    for(int j=3;j>=0;j--) {
        if(j>=count)continue;
        float q=clamp(progress-float(j)*.12*uRoute.z,0.0,1.0);
        float x=mix(uAddress.x,uAddress.y,q);
        float scale=words?1.0:.62;
        vec2 origin=vec2(x-scale*.5,.5-scale*.5-sin(q*3.14159265)*.3);
        vec2 p=(uv-origin)/scale;
        vec4 src=vec4(0);
        if(words)src=Glyph(p,max(0,t-float(j)*.085));
        
        float alpha=(1.0-float(j)/float(count+1))*.95;
        result=Over(src*alpha,result);
    }
    if(words&&progress>.92){
        float x=mix(uAddress.x,uAddress.y,progress);
        for(int k=0;k<10;k++){
            float a=SeedNoise(k)*6.2831853;
            float d=(progress-.9)*6.0*uRoute.w;
            vec2 pos=vec2(x+cos(a)*d,.5+sin(a)*d*640.0/360.0);
            if(all(greaterThanEqual(uv,pos))&&all(lessThan(uv,pos+vec2(8.0/640.0,8.0/360.0))))result=vec4(1,.357,.275,1);
        }
    }
    return result;
}
vec4 Echo(vec2 uv,bool words) {
    vec4 result=vec4(0);int count=int(uEcho.y+.5);
    for(int k=5;k>=1;k--){
        if(k>count||uTime-float(k)*uEcho.x<0)continue;
        float x=(k%2==1?1.0:-1.0)*uEcho.w*.18*float(k)/float(count);
        float y=(float(k)/float(count)-.5)*uEcho.w*.35;
        vec2 p=(uv-vec2((1-uEchoScale)*.5+x,(1-uEchoScale)*.5+y))/uEchoScale;
        if(Inside(p))result=Over(Routed(p,uTime-float(k)*uEcho.x,k,words)*pow(uEcho.z,float(k))*.92,result);
    }
    return result;
}
bool InRegion(vec2 p){return all(greaterThanEqual(p,uRegion.xy))&&all(lessThanEqual(p,uRegion.xy+uRegion.zw));}
vec4 Typography(vec2 uv){
    vec4 result=vec4(0);int count=int(uType.y+.5);
    for(int k=8;k>=0;k--){
        if(k>=count)continue;
        vec2 offset=k==0?vec2(0):vec2(sin(uTime*uDrift+float(k))*.16,cos(uTime*uDrift+float(k))*.18);
        vec2 p=(uv-offset-.5)/max(.01,uType.x/.75)+.5;
        result=Over(Glyph(p,uTime)*vec4(.859,.984,.396,1)*(k==0?1.0:.18),result);
    }
    if(uType.w>.3){
        float strip=floor(uv.y*12.0);
        float dx=sin(strip*4.0+floor(uTime*5.0))*uType.w*.045;
        vec2 p=(uv-vec2(dx,0)-.5)/max(.01,uType.x/.75)+.5;
        result=Over(Glyph(p,uTime)*vec4(.859,.984,.396,1),result);
    }
    return result;
}
void main(){
    vec2 uv=vec2(vUV.x,1-vUV.y);
    vec4 dry=texture(sTD2DInputs[0],vUV.st);
    if(uWet<=0){fragColor=TDOutputSwizzle(dry);return;}
    vec4 picture=Echo(uv,false);
    // Region is the existing authored rectangle, not a claimed performer matte.
    float strip=floor(uv.y*48.0)/48.0;
    float dx=sin(strip*6.2831853*uField.y+uTime*uField.z)*uField.x*.32;
    vec2 displaced=vec2(fract(uv.x-dx),uv.y);
    if(InRegion(uv))picture=Over(vec4(.0314,.0392,.051,1),picture);
    if(InRegion(displaced)&&(uField.w>.5||InRegion(uv)))picture=Over(Echo(displaced,false),picture);
    vec4 text=clamp(Echo(uv,true)+Typography(uv)*.75,0.0,1.0);
    vec4 processed=Over(text,picture);
    processed=vec4(processed.rgb,1);
    fragColor=TDOutputSwizzle(mix(dry,processed,uWet));
}
