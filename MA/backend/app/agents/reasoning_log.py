"""
Reasoning Log - Tracks multi-agent decision-making process
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class ReasoningStepType(str, Enum):
    """Types of reasoning steps"""
    DATA_FETCH = "data_fetch"
    ANALYSIS = "analysis"
    DECISION = "decision"
    WARNING = "warning"
    COORDINATION = "coordination"
    TOOL_USE = "tool_use"


class ReasoningLog:
    """Tracks the chain of thought for multi-agent systems"""
    
    def __init__(self, query_id: str = None):
        self.query_id = query_id or f"query_{datetime.utcnow().timestamp()}"
        self.steps: List[Dict[str, Any]] = []
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
    
    def add_step(
        self,
        agent_name: str,
        step_type: ReasoningStepType,
        description: str,
        data: Optional[Dict[str, Any]] = None,
        result: Optional[Any] = None,
        duration_ms: Optional[float] = None
    ):
        """Add a reasoning step"""
        step = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent_name,
            "type": step_type.value,
            "description": description,
            "data": data or {},
            "result": result,
            "duration_ms": duration_ms
        }
        self.steps.append(step)
        return step
    
    def add_data_fetch(self, agent_name: str, source: str, description: str, duration_ms: float = None):
        """Add a data fetch step"""
        return self.add_step(
            agent_name=agent_name,
            step_type=ReasoningStepType.DATA_FETCH,
            description=f"{source} verisi çekiliyor: {description}",
            data={"source": source},
            duration_ms=duration_ms
        )
    
    def add_analysis(self, agent_name: str, analysis_type: str, description: str, result: Any = None, duration_ms: Optional[float] = None):
        """Add an analysis step"""
        return self.add_step(
            agent_name=agent_name,
            step_type=ReasoningStepType.ANALYSIS,
            description=f"{analysis_type} analizi: {description}",
            data={"analysis_type": analysis_type},
            result=result,
            duration_ms=duration_ms
        )
    
    def add_decision(self, agent_name: str, decision: str, reasoning: str, confidence: float = None, duration_ms: Optional[float] = None):
        """Add a decision step"""
        return self.add_step(
            agent_name=agent_name,
            step_type=ReasoningStepType.DECISION,
            description=f"Karar: {decision}",
            data={"decision": decision, "reasoning": reasoning, "confidence": confidence},
            result={"decision": decision},
            duration_ms=duration_ms
        )
    
    def add_warning(self, agent_name: str, warning: str, severity: str = "medium"):
        """Add a warning step"""
        return self.add_step(
            agent_name=agent_name,
            step_type=ReasoningStepType.WARNING,
            description=f"Uyarı: {warning}",
            data={"warning": warning, "severity": severity},
            result={"warning": warning}
        )
    
    def add_coordination(self, from_agent: str, to_agent: str, message: str, data: Any = None):
        """Add a coordination step between agents"""
        return self.add_step(
            agent_name=from_agent,
            step_type=ReasoningStepType.COORDINATION,
            description=f"{from_agent} → {to_agent}: {message}",
            data={"from": from_agent, "to": to_agent, "message": message},
            result=data
        )
    
    def add_tool_use(self, agent_name: str, tool_name: str, input_data: Any, output_data: Any = None):
        """Add a tool use step"""
        return self.add_step(
            agent_name=agent_name,
            step_type=ReasoningStepType.TOOL_USE,
            description=f"Araç kullanımı: {tool_name}",
            data={"tool": tool_name, "input": input_data},
            result=output_data
        )
    
    def finalize(self):
        """Finalize the reasoning log"""
        self.end_time = datetime.utcnow()
        total_duration = (self.end_time - self.start_time).total_seconds() * 1000
        return {
            "query_id": self.query_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_duration_ms": total_duration,
            "steps": self.steps,
            "step_count": len(self.steps),
            "agents_involved": list(set(step["agent"] for step in self.steps))
        }
    
    def get_summary(self) -> str:
        """Get a human-readable summary of the reasoning chain"""
        if not self.steps:
            return "Henüz adım yok."
        
        summary_parts = []
        for i, step in enumerate(self.steps, 1):
            agent = step["agent"]
            desc = step["description"]
            step_type = step["type"]
            
            icon = {
                "data_fetch": "📥",
                "analysis": "🔍",
                "decision": "✅",
                "warning": "⚠️",
                "coordination": "🤝",
                "tool_use": "🔧"
            }.get(step_type, "•")
            
            summary_parts.append(f"{i}. {icon} {agent}: {desc}")
        
        return "\n".join(summary_parts)








