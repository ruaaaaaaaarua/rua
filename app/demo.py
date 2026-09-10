"""Explicit sample workspace. Never used to answer real uploaded questions."""
from .store import uid,message

def create_demo(store):
    s=store.create_session('示例 · 电力系统分析',demo=True)
    samples=[
        ('1','single','在电阻不变的情况下，电流变为原来的 2 倍，电阻消耗的功率变为原来的多少倍？',[('A','2 倍'),('B','4 倍'),('C','1/2 倍'),('D','不变')],'B','P = I²R','certain','B','焦耳定律','电阻不变时，功率与电流的平方成正比。',True,''),
        ('2','single','三相对称星形连接中，线电压与相电压的幅值关系是？',[('A','相等'),('B','线电压是相电压的 √3 倍'),('C','线电压是相电压的 3 倍'),('D','相电压是线电压的 √3 倍')],'B','星形连接，线电压是相电压的√3倍','certain','B','线电压与相电压','对称星形连接中，线电压幅值为相电压的 √3 倍。',True,''),
        ('3','single','忽略线路电阻，两端电压和功角不变时，线路电抗增大，传输有功功率如何变化？',[('A','增大'),('B','减小'),('C','不变'),('D','无法判断')],'A','电抗越大，功率越大','certain','B','功角关系','两端电压与功角不变时，有功功率与线路电抗成反比。',False,'你写的比例关系反了：公式中电抗在分母。'),
        ('4','judge','在正弦交流稳态中，电感元件的电流相位滞后于其端电压。',[], '√','电感电流不能突变？','unsure','TRUE','电感的相位关系','理想电感在正弦稳态下，电流相位滞后电压 90°。',True,'相位关系应由正弦稳态关系判断；“电流不能突变”描述的是时域连续性，两者不能直接替代。'),
        ('5','multiple','下列哪些因素会影响理想长线路的自然功率？',[('A','额定电压'),('B','波阻抗'),('C','负荷功率因数'),('D','线路实际输送的有功功率')],'AB','Pn = U² / Zc','certain','AB','自然功率','自然功率由电压与波阻抗决定，注意平方关系。',True,'')]
    for n,kind,text,options,answer,reasoning,confidence,correct,kp,point,ok,diag in samples:
        s['questions'].append(dict(id=uid(),number=n,kind=kind,text=text,options=[dict(key=k,text=v) for k,v in options],
            user_answer=answer,reasoning=reasoning,confidence=confidence,subject='电力系统分析',chapter='基础关系',knowledge=kp,revealed=True,
            analysis=dict(correct=ok,answer=correct,knowledge_point=point,diagnosis=diag,
                distinction=diag if confidence=='unsure' else '',hint='检查固定条件与公式中的比例关系。',explanation=point,
                reasoning_ok=None if confidence=='unsure' else ok,error_type='reasoning_error' if not ok else 'unknown',status='confirmed',source='demo')))
    s['messages']=[message('system','演示工作区 · 以下为预设示例，不会调用模型，也不会写入你的真实知识状态。'),
        message('assistant','已整理这一页。先看整体，再选择你想深入的地方。','overview')]
    store.save_session(s)
    return s
