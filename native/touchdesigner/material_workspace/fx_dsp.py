"""Causal streaming DSP for the retained rack; bounded stereo history."""
import math
import numpy as np


class Stream:
    def __init__(self,rate=44100,seconds=32,seed=1):
        self.rate=rate;self.capacity=int(rate*seconds)
        self.input=np.zeros((2,self.capacity),np.float32)
        self.output=np.zeros_like(self.input);self.position=0
        self.random=np.random.default_rng(seed);self.grains=[];self.next_grain=0
        self.captured=None;self.queue=[];self.playing=[];self.next_arrival=0;self.next_release=0

    def read(self,buffer,indices):
        indices=np.asarray(indices);low=np.floor(indices).astype(np.int64);fraction=indices-low
        valid=(low>=max(0,self.position-self.capacity))&(low<self.position)
        result=buffer[:,low%self.capacity]*(1-fraction)+buffer[:,np.minimum(low+1,self.position-1)%self.capacity]*fraction
        return result*valid

    def write(self,buffer,data,start):
        if data.shape[1]>self.capacity:
            start+=data.shape[1]-self.capacity;data=data[:,-self.capacity:]
        buffer[:,(start+np.arange(data.shape[1]))%self.capacity]=data

    def process(self,kind,a,p):
        a=np.asarray(a,dtype=np.float32)
        if a.shape[0]==1:a=np.repeat(a,2,axis=0)
        a=a[:2];n=a.shape[1];start=self.position;indices=start+np.arange(n);t=indices/self.rate
        self.write(self.input,a,start);self.position+=n
        value=lambda name,default:float(p.get(name,default))
        def past(offset):return self.read(self.input,indices-offset*self.rate)
        if kind=='routing':
            phase=(t/max(.08,value('travel',.6)))%2;progress=np.where(phase<1,phase,2-phase)
            pan=np.clip(.5+(value('origin',.08)+(value('destination',.92)-value('origin',.08))*progress-.5)*value('spread',.9),0,1)
            mono=a.mean(axis=0);b=np.array([mono*np.cos(pan*np.pi/2),mono*np.sin(pan*np.pi/2)])*np.sqrt(2)
        elif kind=='delay':
            b=np.zeros_like(a);norm=0
            for tap in range(1,min(8,max(1,int(value('taps',5))))+1):
                gain=value('decay',.68)**(tap-1);pan=.5+(-.5 if tap%2 else .5)*value('spread',.78)
                mono=past(value('time',.48)*tap).mean(axis=0)
                b+=np.array([mono*math.cos(pan*np.pi/2),mono*math.sin(pan*np.pi/2)])*math.sqrt(2)*gain;norm+=gain*gain
            b/=max(1,math.sqrt(norm))
        elif kind in ['stutter','freeze']:
            capture=value('capture',2.88 if kind=='stutter' else 2.92)
            width=value('window',.24) if kind=='stutter' else value('grain',.08)
            length=max(16,int(width*self.rate));ready=int((capture+width)*self.rate)
            if self.captured is None and self.position>=ready:
                self.captured=self.read(self.input,int(capture*self.rate)+np.arange(length)).copy()
            b=a.copy()
            if self.captured is not None:
                elapsed=t-capture-width
                if kind=='stutter':
                    speed=max(.25,value('rate',1));period=width/speed+value('gap',.035)
                    phase=elapsed%period;active=(elapsed>=0)&(elapsed<period*min(40,int(value('repeats',16))))
                    read=(phase*speed*self.rate)%length;gate=phase<width/speed
                    fade=np.minimum(1,np.minimum(phase/0.003,(width/speed-phase)/.003));fade=np.clip(fade,0,1)*gate
                    fade*=np.clip((period*min(40,int(value('repeats',16)))-elapsed)/max(1/self.rate,value('release',.03)),0,1)
                else:
                    phase=(elapsed*self.rate)%length;read=phase
                    active=(elapsed>=0)&(elapsed<value('duration',4.4))
                    fade=np.exp(-value('decay',.12)*np.maximum(0,elapsed))*np.clip(elapsed/.006,0,1)
                    fade*=np.clip((value('duration',4.4)-elapsed)/max(.005,value('release',.05)),0,1)
                left=np.floor(read).astype(int);fraction=read-left
                held=self.captured[:,left%length]*(1-fraction)+self.captured[:,(left+1)%length]*fraction
                if kind=='freeze':
                    second=self.captured[:,(left+length//2)%length];w=.5-.5*np.cos(2*np.pi*read/length);held=held*w+second*(1-w)
                b[:,active]=held[:,active]*fade[active]
        elif kind=='granular':
            b=np.zeros_like(a);weights=np.zeros(n)
            while self.next_grain<self.position:
                size=max(16,int(value('size',.07)*self.rate));shuffle=value('order',1)
                source=max(0,self.next_grain-self.random.random()*value('scatter',.7)*self.rate*shuffle)
                speed=2**((self.random.random()*2-1)*value('pitch',7)*shuffle/12)
                pan=.5+(self.random.random()-.5)*value('spatial',.95)
                self.grains.append((self.next_grain,size,source,speed,pan));self.next_grain+=max(1,int(self.rate/max(2,value('density',30))))
            self.grains=[g for g in self.grains if g[0]+g[1]>start][-128:]
            for onset,size,source,speed,pan in self.grains:
                phase=indices-onset;active=(phase>=0)&(phase<size);window=(.5-.5*np.cos(2*np.pi*phase/max(1,size-1)))*active
                grain=self.read(self.input,source+phase*speed)
                b[0]+=grain[0]*window*math.cos(pan*np.pi/2)*math.sqrt(2);b[1]+=grain[1]*window*math.sin(pan*np.pi/2)*math.sqrt(2);weights+=window
            b/=np.maximum(1,weights)
        elif kind=='reverse':
            if int(value('mode',0))==1:b=a[::-1].copy()
            else:
                span=max(.15,value('span',2.2));pivot=value('pivot',4);block=np.floor((t-pivot)/span)*span+pivot
                # Causal adapter: reverse the previous complete interval, with one span latency.
                source=block-((t-block)*value('speed',1))%span-1/self.rate
                b=self.read(self.input,source*self.rate)
        elif kind=='feedback':
            delay=max(1,int(value('time',.26)*self.rate));b=np.zeros_like(a)
            gain=min(.9,max(0,value('gain',.8)));repeats=min(16,max(1,int(value('repeats',10))))
            epoch=max(delay,min(delay*repeats,int(value('reset',11.5)*self.rate)));threshold=value('threshold',.005)
            for offset in range(0,n,delay):
                count=min(delay,n-offset);at=indices[offset:offset+count]
                returned=self.read(self.output,at-delay);returned[:,(at%epoch)<delay]=0
                returned[np.abs(returned)<threshold]=0
                b[:,offset:offset+count]=a[:,offset:offset+count]+gain*returned
                self.write(self.output,b[:,offset:offset+count],start+offset)
        elif kind=='queue':
            b=np.zeros_like(a);capacity=min(24,max(2,int(value('capacity',7))))
            while self.next_arrival<self.position:
                length=max(16,int(.08*self.rate));snippet=self.read(self.input,self.next_arrival-length+np.arange(length)).copy()
                self.queue.append(snippet);self.queue=self.queue[-capacity:];self.next_arrival+=max(1,int(self.rate/max(.25,value('rate',7))))
            while self.next_release<self.position:
                if self.queue:
                    snippet=self.queue.pop(-1 if int(value('order',0)) else 0)
                    pan=.5+(self.random.random()-.5)*value('spread',.95)
                    self.playing.append((self.next_release,snippet,pan))
                self.next_release+=max(1,int(self.rate/max(.25,value('release',1.2))))
            # Burst opens a finite retained queue once per authored interval.
            if start//max(1,int(value('burst',3.4)*self.rate)) != (self.position-1)//max(1,int(value('burst',3.4)*self.rate)):
                for snippet in self.queue:
                    pan=.5+(self.random.random()-.5)*value('spread',.95)
                    self.playing.append((start,snippet/math.sqrt(max(1,len(self.queue))),pan))
                self.queue=[]
            self.playing=[entry for entry in self.playing if entry[0]+entry[1].shape[1]>start][-128:]
            for onset,snippet,pan in self.playing:
                left=max(start,onset);right=min(self.position,onset+snippet.shape[1])
                if right>left:
                    source=snippet[:,left-onset:right-onset].mean(axis=0)
                    b[0,left-start:right-start]+=source*math.cos(pan*np.pi/2)*math.sqrt(2)
                    b[1,left-start:right-start]+=source*math.sin(pan*np.pi/2)*math.sqrt(2)
        elif kind=='gate':
            phase=(t/max(.1,value('period',1.3))+value('phase',.1))%1
            detector=np.full(n,value('control',0)) if 'control' in p else np.max(np.abs(a),axis=0)
            open_=detector>=value('threshold',.38) if int(value('detector',0)) else phase<value('duty',.18)
            b=a*np.where(open_,1,value('retain',0))
        elif kind=='displacement':
            warp=np.sin(t*2*np.pi*value('frequency',4.2))*value('warp',.036)
            b=self.read(self.input,indices-(np.abs(warp))*self.rate)
            ring=np.sin(t*2*np.pi*value('frequency',4.2)*31);blend=value('ring',.25);b*=1-blend+blend*ring
        elif kind=='exchange':
            b=past(value('timeOffset',.45))
            swap=(np.floor(t/max(.12,value('interval',.72))).astype(int)*int(value('offset',1)))%2!=0
            b[:,swap]=b[::-1,swap]
        elif kind=='damage':
            step=max(1,int(self.rate/max(600,value('rate',3200))));sample=self.read(self.input,(indices//step)*step)
            bits=min(16,max(2,int(value('bits',3))));levels=2**(bits-1)-1
            b=np.round(np.tanh(sample*value('drive',2.6))*levels)/levels*value('output',.7)
            # Bounded one-pole lowpass; state persists between blocks.
            alpha=1-math.exp(-2*math.pi*min(value('band',900),self.rate*.45)/self.rate)
            previous=getattr(self,'lowpass',np.zeros(2))
            for i in range(n):previous=previous+alpha*(b[:,i]-previous);b[:,i]=previous
            self.lowpass=previous
        else:b=a.copy()  # Typography is visual-only by the retained contract.
        return np.clip(np.nan_to_num(b),-8,8).astype(np.float32)
