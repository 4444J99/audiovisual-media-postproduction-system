// Experimental native causal texture histories. Live validation required.
uniform vec4 uControl; // type, elapsed, wet, intensity
uniform vec4 uPort; // port, history fps, seed, phase
uniform vec4 uAux; // admitted
uniform vec4 uP0;
uniform vec4 uP1;
uniform vec4 uP2;
out vec4 fragColor;
vec4 Sample(vec2 uv) {
    if (any(lessThan(uv,vec2(0))) || any(greaterThan(uv,vec2(1)))) return vec4(0);
    return texture(sTD2DInputs[0],uv);
}
vec4 Over(vec4 front,vec4 back) {return front+back*(1.-front.a);}
vec4 History(int slot,vec2 uv) {
 if(any(lessThan(uv,vec2(0)))||any(greaterThan(uv,vec2(1)))) return vec4(0);
 slot-=int(uAux.y);
 if(slot<0 || slot>=8)return vec4(0);
 switch(slot) {
#if TD_NUM_2D_INPUTS > 1
case 0: return texture(sTD2DInputs[1],uv);
#endif
#if TD_NUM_2D_INPUTS > 2
case 1: return texture(sTD2DInputs[2],uv);
#endif
#if TD_NUM_2D_INPUTS > 3
case 2: return texture(sTD2DInputs[3],uv);
#endif
#if TD_NUM_2D_INPUTS > 4
case 3: return texture(sTD2DInputs[4],uv);
#endif
#if TD_NUM_2D_INPUTS > 5
case 4: return texture(sTD2DInputs[5],uv);
#endif
#if TD_NUM_2D_INPUTS > 6
case 5: return texture(sTD2DInputs[6],uv);
#endif
#if TD_NUM_2D_INPUTS > 7
case 6: return texture(sTD2DInputs[7],uv);
#endif
#if TD_NUM_2D_INPUTS > 8
case 7: return texture(sTD2DInputs[8],uv);
#endif
#if TD_NUM_2D_INPUTS > 9
case 8: return texture(sTD2DInputs[9],uv);
#endif
#if TD_NUM_2D_INPUTS > 10
case 9: return texture(sTD2DInputs[10],uv);
#endif
#if TD_NUM_2D_INPUTS > 11
case 10: return texture(sTD2DInputs[11],uv);
#endif
#if TD_NUM_2D_INPUTS > 12
case 11: return texture(sTD2DInputs[12],uv);
#endif
#if TD_NUM_2D_INPUTS > 13
case 12: return texture(sTD2DInputs[13],uv);
#endif
#if TD_NUM_2D_INPUTS > 14
case 13: return texture(sTD2DInputs[14],uv);
#endif
#if TD_NUM_2D_INPUTS > 15
case 14: return texture(sTD2DInputs[15],uv);
#endif
#if TD_NUM_2D_INPUTS > 16
case 15: return texture(sTD2DInputs[16],uv);
#endif
#if TD_NUM_2D_INPUTS > 17
case 16: return texture(sTD2DInputs[17],uv);
#endif
#if TD_NUM_2D_INPUTS > 18
case 17: return texture(sTD2DInputs[18],uv);
#endif
#if TD_NUM_2D_INPUTS > 19
case 18: return texture(sTD2DInputs[19],uv);
#endif
#if TD_NUM_2D_INPUTS > 20
case 19: return texture(sTD2DInputs[20],uv);
#endif
#if TD_NUM_2D_INPUTS > 21
case 20: return texture(sTD2DInputs[21],uv);
#endif
#if TD_NUM_2D_INPUTS > 22
case 21: return texture(sTD2DInputs[22],uv);
#endif
#if TD_NUM_2D_INPUTS > 23
case 22: return texture(sTD2DInputs[23],uv);
#endif
#if TD_NUM_2D_INPUTS > 24
case 23: return texture(sTD2DInputs[24],uv);
#endif
#if TD_NUM_2D_INPUTS > 25
case 24: return texture(sTD2DInputs[25],uv);
#endif
#if TD_NUM_2D_INPUTS > 26
case 25: return texture(sTD2DInputs[26],uv);
#endif
#if TD_NUM_2D_INPUTS > 27
case 26: return texture(sTD2DInputs[27],uv);
#endif
#if TD_NUM_2D_INPUTS > 28
case 27: return texture(sTD2DInputs[28],uv);
#endif
#if TD_NUM_2D_INPUTS > 29
case 28: return texture(sTD2DInputs[29],uv);
#endif
#if TD_NUM_2D_INPUTS > 30
case 29: return texture(sTD2DInputs[30],uv);
#endif
#if TD_NUM_2D_INPUTS > 31
case 30: return texture(sTD2DInputs[31],uv);
#endif
#if TD_NUM_2D_INPUTS > 32
case 31: return texture(sTD2DInputs[32],uv);
#endif
 } return vec4(0);
}
float Hash(float x) {return fract(sin(x*127.1+uPort.z*311.7)*43758.5453);}
void main() {
    vec2 uv=vUV.st;vec4 dry=Sample(uv),wet=dry;
    int kind=int(uControl.x);float t=uControl.y;
    if(kind==0) {
        wet=vec4(0);float phase=mod(t/max(.08,uP0.x),2.);float progress=phase<1.?phase:2.-phase;
        for(int k=7;k>=0;k--)if(k<int(uP0.y)) {
            float q=clamp(progress-float(k)*.12*uP0.z,0.,1.);
            float x=mix(uP1.x,uP1.y,q);vec2 pos=vec2(x,.5+sin(q*3.14159)*.3);
            vec2 traceUV=(uv-pos)/.62+.5;vec4 trace=k==0?Sample(traceUV):History(k,traceUV);
            wet=Over(trace*(1.-float(k)/(uP0.y+1.)),wet);
        }
    } else if(kind==1) {
        wet=dry;
        for(int i=7;i>=0;i--) if(i<int(uP0.y)) {
            float scale=pow(max(.25,uP1.x),float(i+1));
            vec2 shift=vec2((float(i%2)*2.-1.)*uP0.w*.14*float(i+1),0);
            wet=Over(History(i,(uv-.5-shift)/scale+.5)*pow(uP0.z,float(i+1)),wet);
        }
    } else if(kind==2) {
        float start=uP1.y,width=uP0.x,period=width/max(.25,uP0.z)+uP0.w;
        float phase=mod(t-start-width,period);
        if(t>=start+width && t<start+width+period*uP0.y) {
            float edge=max(.002,uP1.x);
            float gate=smoothstep(0.,edge,phase)*(1.-smoothstep(width/max(.25,uP0.z)-edge,width/max(.25,uP0.z),phase));
            wet=History(0,uv)*gate;
        }
    } else if(kind==3) {
        float divisions=max(2.,uP1.y);vec2 cell=floor(uv*divisions);float id=cell.x+cell.y*divisions;
        float seed=floor(t*max(2.,uP0.y))+id;
        vec2 q=uv+(vec2(Hash(seed),Hash(seed+41.))-.5)*uP1.x*.25;
        wet=History(int(floor(Hash(seed+17.)*5.)),fract(q));
    } else if(kind==4) {
        if(int(uP0.w)==0) {if(t>=uP0.x) wet=History(0,uv);}
        else {float phase=fract(t/max(.15,uP0.x)*uP0.y);wet=Sample(uv-vec2(.5-phase,0));}
    } else if(kind==5) {
        float start=uP0.x+uP0.z;
        if(t>=start && t<start+uP0.y) {
            float fade=exp(-uP0.w*(t-start));
            vec2 q=uv-vec2(sin(t)*uP1.x*.035,0);
            wet=mix(dry,History(0,q),fade);
        }
    } else if(kind==6) {
        float angle=radians(uP1.x);vec2 v=(uv-.5)/max(.1,uP0.w);
        vec2 q=mat2(cos(angle),-sin(angle),sin(angle),cos(angle))*v+.5;
        vec4 echo=History(0,q)*uP0.y;
        if(max(max(echo.r,echo.g),echo.b)<uP1.z) echo=vec4(0);
        wet=Over(echo,dry);
    } else if(kind==7) {
        float phase=uPort.w;
        int count=min(int(uP0.x),max(0,int(floor(phase*uP0.y)-floor(phase*uP0.z*.2))));
        wet=dry;
#if TD_NUM_2D_INPUTS > 9
        if(uAux.y>0.)wet=texture(sTD2DInputs[9],uv);
#endif
        for(int i=23;i>=0;i--) if(i<count) {
            float spread=uP1.x;vec2 pos=vec2(.5+(Hash(float(i))-.5)*spread,.5+(Hash(float(i+51))-.5)*spread);
            wet=Over(History(i,(uv-pos)/.45+.5)*.8,wet);
        }
    } else if(kind==8) {
        float phase=fract(t/max(.1,uP0.y)+uP0.w);float edge=max(.0001,uP0.z/max(.1,uP0.y));float gate=smoothstep(0.,edge,phase)*(1.-smoothstep(max(0.,uP0.x-edge),uP0.x,phase));if(uP1.z>.5)gate=step(uP1.y,uControl.w);wet=dry*mix(uP1.x,1.,gate);
    } else if(kind==9) {
        float amount=uP0.x*.32;vec2 q=uv;
        if(int(uP1.y)==1)q.y+=sin(uv.x*6.28318*uP0.y+t*uP0.w)*amount;
        else if(int(uP1.y)==2){vec2 v=uv-.5;float a=sin(t*uP0.w+length(v)*uP0.y)*amount;q=.5+mat2(cos(a),-sin(a),sin(a),cos(a))*v;}
        else q.x+=sin(uv.y*6.28318*uP0.y+t*uP0.w)*amount;
        wet=Sample(fract(q));
    } else if(kind==10) {
        if(int(uP1.x)!=1) {
            float stepper=floor(t/max(.12,uP0.z));float shifted=mod(floor(uv.x*4.)+stepper*uP0.x,4.);
            vec2 q=vec2((shifted+fract(uv.x*4.))/4.,uv.y);
            wet=uP0.w>0.?History(0,q):Sample(q);
        }
    } else if(kind==11 && int(uPort.x)==1) {
        wet=vec4(0);
#if TD_NUM_2D_INPUTS > 9
        if(uAux.y>0.)wet=texture(sTD2DInputs[9],uv);
#endif
        int copies=int(uP0.y);
        for(int i=31;i>=0;i--) if(i<copies && i>=int(uAux.y) && i<int(uAux.y)+8) {
            vec2 pos=vec2(.5)+vec2(sin(t*uP1.y+float(i)),cos(t*uP1.y+float(i)))*.16;
            vec2 q=(uv-pos)/max(.05,uP0.x)+.5;
            q.x+=sin(floor(q.y*12.)*4.+floor(t*5.))*uP0.w*.045;
            vec4 glyph=int(uP1.x)==2?History(i,q):Sample(q);
            if(int(uP1.x)==2)glyph*=exp(-float(i)*.32/max(.1,uP0.z));
            wet=Over(glyph,wet);
        }
    } else if(kind==11 && int(uPort.x)==2) {
        wet=dry;
    } else if(kind==11) {
        vec4 word=texture(sTD2DInputs[1],uv);
        wet=int(uP1.x)==1?dry*word.a:Over(word,dry);
    } else if(kind==12) {
        float cols=max(3.,round(1./max(.003,uP0.z)));vec2 grid=vec2(cols,max(2.,round(cols*uTDOutputInfo.res.w/uTDOutputInfo.res.z)));
        vec4 p=Sample((floor(uv*grid)+.5)/grid);float levels=max(1.,uP0.w-1.);
        float gray=dot(p.rgb,vec3(.333333));gray=round(clamp((gray-.5)*uP1.x+.5,0.,1.)*levels)/levels;
        wet=vec4(vec3(.847,.949,1.)*gray,p.a);
    }
    fragColor=TDOutputSwizzle(uAux.z>.5?mix(dry,wet,clamp(uControl.z,0.,1.)):wet);
}
