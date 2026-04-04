import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bot, X, Send, Sparkles, User, FileText, Activity } from 'lucide-react';
import './AIManagerAssistant.css';

export default function AIManagerAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { id: 1, type: 'agent', text: 'Hello! I am your AI Management Copilot. How can I assist you with your workforce today?', options: ['Summarize metrics', 'Export directory report', 'Audit recent changes'] }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) scrollToBottom();
  }, [messages, isOpen]);

  const handleSend = (text = input) => {
    if (!text.trim()) return;

    // Add user message
    const userMsg = { id: Date.now(), type: 'user', text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    // Mock agent response
    setTimeout(() => {
      let responseText = 'I am processing your command...';
      let options = [];

      const lowerText = text.toLowerCase();
      if (lowerText.includes('summarize') || lowerText.includes('metrics')) {
         responseText = 'Based on current data, you have 0 active interns and 3 full-time employees. Engagement is high across all active programs.';
         options = ['View People Dashboard'];
      } else if (lowerText.includes('export') || lowerText.includes('report')) {
         responseText = 'I have analyzed the roster. A comprehensive CSV export request has been prepared. This requires final admin approval.';
         options = ['View Pending Approvals'];
      } else if (lowerText.includes('audit')) {
         responseText = 'The latest security audits show 2 role adjustments in the engineering cohort and 1 new laptop provisioned.';
      } else {
         responseText = "I've noted your request. I am currently operating in limited preview mode. For now, I can help summarize cohort metrics, request HR reports, and audit changes.";
      }

      setMessages(prev => [...prev, { id: Date.now() + 1, type: 'agent', text: responseText, options }]);
      setIsTyping(false);
    }, 1200);
  };

  return (
    <>
      {/* Floating Action Button */}
      <motion.button
        className="ai-fab-button"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(true)}
        initial={false}
        animate={{ scale: isOpen ? 0 : 1, opacity: isOpen ? 0 : 1 }}
      >
        <Sparkles size={24} />
      </motion.button>

      {/* Copilot Sidebar / Modal Overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="ai-copilot-container glass-panel"
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 50, scale: 0.9 }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          >
            <div className="ai-copilot-header">
              <div className="ai-header-title">
                 <Bot size={20} color="var(--color-primary)" />
                 <span>Management Copilot</span>
              </div>
              <button className="ai-close-btn" onClick={() => setIsOpen(false)}>
                <X size={20} />
              </button>
            </div>

            <div className="ai-scroll-area">
              {messages.map(msg => (
                <div key={msg.id} className={`ai-message-row ${msg.type === 'user' ? 'row-user' : 'row-agent'}`}>
                   {msg.type === 'agent' && <div className="ai-avatar"><Bot size={14}/></div>}
                   <div className={`ai-message-bubble ${msg.type === 'user' ? 'bubble-user' : 'bubble-agent'}`}>
                     <p>{msg.text}</p>
                     {msg.options && msg.options.length > 0 && (
                        <div className="ai-pill-options">
                           {msg.options.map((opt, i) => (
                             <button key={i} className="ai-pill-btn" onClick={() => handleSend(opt)}>{opt}</button>
                           ))}
                        </div>
                     )}
                   </div>
                </div>
              ))}
              {isTyping && (
                <div className="ai-message-row row-agent">
                   <div className="ai-avatar"><Bot size={14}/></div>
                   <div className="ai-message-bubble bubble-agent typing-indicator">
                     <span></span><span></span><span></span>
                   </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="ai-copilot-input-area">
               <input
                 type="text"
                 placeholder="Command the AI Copilot..."
                 value={input}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && handleSend()}
               />
               <button className="ai-send-btn" onClick={() => handleSend()}>
                 <Send size={18} />
               </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
