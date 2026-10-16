// Native stateless picture stage. Temporal ports remain explicitly pending.
uniform vec4 uControl; // type, elapsed, wet, intensity
uniform vec4 uP0;
uniform vec4 uP1;
uniform vec4 uP2;
out vec4 fragColor;
vec4 Sample(vec2 uv) {
    if (any(lessThan(uv,vec2(0))) || any(greaterThan(uv,vec2(1)))) return vec4(0);
    return texture(sTD2DInputs[0],uv);
}
vec4 Over(vec4 front,vec4 back) {return front+back*(1.-front.a);}
void main() {
    vec2 uv=vUV.st;vec4 dry=Sample(uv),wet=dry;
    int kind=int(uControl.x);float t=uControl.y;
    if(kind==0) {
        wet=vec4(0);float phase=mod(t/max(.08,uP0.x),2.);float progress=phase<1.?phase:2.-phase;
        for(int k=7;k>=0;k--)if(k<int(uP0.y)) {
            float q=clamp(progress-float(k)*.12*uP0.z,0.,1.);
            float x=mix(uP1.x,uP1.y,q);vec2 pos=vec2(x,.5+sin(q*3.14159)*.3);
            wet=Over(Sample((uv-pos)/.62+.5)*(1.-float(k)/(uP0.y+1.)),wet);
        }
    } else if(kind==8) {
        float phase=fract(t/max(.1,uP0.y)+uP0.w);float gain=phase<uP0.x?1.:uP1.x;wet=dry*gain;
    } else if(kind==9) {
        float amount=uP0.x*.32;vec2 q=uv;
        if(int(uP1.y)==1)q.y+=sin(uv.x*6.28318*uP0.y+t*uP0.w)*amount;
        else if(int(uP1.y)==2){vec2 v=uv-.5;float a=sin(t*uP0.w+length(v)*uP0.y)*amount;q=.5+mat2(cos(a),-sin(a),sin(a),cos(a))*v;}
        else q.x+=sin(uv.y*6.28318*uP0.y+t*uP0.w)*amount;
        wet=Sample(fract(q));
    } else if(kind==11) {
        vec2 q=(uv-.5)/max(.05,uP0.x)+.5;vec4 word=texture(sTD2DInputs[1],q);
        if(int(uP1.x)==1)wet=dry*word.a;
        else if(int(uP1.x)==2) {
            vec2 tile=fract(uv*vec2(3.,max(2.,ceil(uP0.y/3.))));word=texture(sTD2DInputs[1],tile);
            wet=Over(vec4(vec3(.86,.98,.4)*word.a,word.a),dry);
        } else {
            wet=dry;
            for(int k=31;k>=0;k--)if(k<int(uP0.y)) {
                vec2 offset=k==0?vec2(0):vec2(sin(t*uP1.y+float(k)),cos(t*uP1.y+float(k)))*.16;
                vec2 p=q-offset;p.x+=sin(floor(p.y*12.)*4.+floor(t*5.))*uP0.w*.045;
                float alpha=texture(sTD2DInputs[1],p).a*(k==0?1.:.18);
                wet=Over(vec4(vec3(.86,.98,.4)*alpha,alpha),wet);
            }
        }
    } else if(kind==12) {
        float cols=max(3.,round(1./max(.003,uP0.z)));vec2 grid=vec2(cols,max(2.,round(cols*uTDOutputInfo.res.w/uTDOutputInfo.res.z)));
        vec4 p=Sample((floor(uv*grid)+.5)/grid);float levels=max(1.,uP0.w-1.);
        float gray=dot(p.rgb,vec3(.333333));gray=round(clamp((gray-.5)*uP1.x+.5,0.,1.)*levels)/levels;
        wet=vec4(vec3(.847,.949,1.)*gray,p.a);
    }
    fragColor=TDOutputSwizzle(mix(dry,wet,clamp(uControl.z,0.,1.)));
}
