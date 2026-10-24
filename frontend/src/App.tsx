import { useState, useCallback } from 'react';
import { Layers, Image as ImageIcon, FileVideo, Music, FileText, LogOut, LogIn, Loader2, Zap } from 'lucide-react';
import { useAuth0 } from '@auth0/auth0-react';
import DetectorTab from './components/DetectorTab';
import ImageDetectorTab from './components/ImageDetectorTab';
import DocumentDetectorTab from './components/DocumentDetectorTab';
import drishtiLogo from './assets/drishtilogo.png';

type TabType = 'COMBINED' | 'IMAGE' | 'VIDEO' | 'AUDIO' | 'DOCUMENT';

function App() {
  const { isAuthenticated, isLoading, loginWithRedirect, logout, user } = useAuth0();
  const [activeTab, setActiveTab] = useState<TabType>('COMBINED');
  const [credits, setCredits] = useState<number>(1000);
  const [pictureFailed, setPictureFailed] = useState(false);

  const handlePictureError = useCallback(() => setPictureFailed(true), []);

  const TABS = [
    { id: 'COMBINED', label: 'All-in-One Detector', icon: Layers, accept: 'image/*,video/*,audio/*', desc: 'Upload any image, video, or audio file. Our multimodal AI engine will automatically route it to the appropriate model for deepfake analysis.' },
    { id: 'IMAGE', label: 'Image Forensics', icon: ImageIcon, accept: 'image/*', desc: 'Uses a pretrained image classifier to check for signs of AI-generated imagery.' },
    { id: 'VIDEO', label: 'Video Analysis', icon: FileVideo, accept: 'video/*', desc: 'Uses face crops, EfficientNet-B4 and an LSTM to classify sampled video segments.' },
    { id: 'AUDIO', label: 'Audio & Voice', icon: Music, accept: 'audio/*', desc: 'Combines Wav2Vec2 predictions with spectral, pitch and other signal checks.' },
    { id: 'DOCUMENT', label: 'Document Forensics', icon: FileText, accept: 'application/pdf,.pdf', desc: 'Checks PDF metadata, structure, image recompression patterns, text consistency and signature indicators.' }
  ];

  const currentTabInfo = TABS.find(t => t.id === activeTab);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center text-indigo-500">
        <Loader2 className="animate-spin mb-4" size={48} />
        <p className="text-indigo-600 text-lg animate-pulse font-bold">Loading secure environment...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-800 flex items-center justify-center p-8 font-sans antialiased selection:bg-indigo-200">
        <div className="clay-card p-10 max-w-lg w-full text-center space-y-8 relative overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-32 bg-indigo-100 blur-[80px] pointer-events-none" />

          <div className="flex items-center justify-center space-x-3 mx-auto">
            <img src={drishtiLogo} alt="Drishti Logo" className="h-28 w-auto object-contain" />
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight text-slate-800 pb-1">
            Welcome to <span className="text-indigo-600">Drishti</span>
          </h1>

          <p className="text-slate-500 text-lg leading-relaxed font-medium">
            Detect the fake. Protect the truth.
            <br />
            Please authenticate to access the forensic tools.
          </p>

          <button
            onClick={() => loginWithRedirect()}
            className="clay-btn flex items-center justify-center w-full space-x-2 py-4 px-6"
          >
            <LogIn size={20} />
            <span className="text-lg">Secure Login with Auth0</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 p-8 font-sans antialiased selection:bg-indigo-200">
      <div className="max-w-5xl mx-auto space-y-10 relative">

        <header className="relative text-center space-y-4 pt-12 mt-4">
          {/* User Profile & Logout Button */}
          <div className="absolute -top-4 right-0 flex items-center mb-6 space-x-4">

            {/* Credit Display */}
            <div className="hidden sm:flex items-center space-x-2 bg-amber-50 px-4 py-2.5 rounded-2xl border border-amber-200 min-w-max">
              <Zap size={18} className="text-amber-500" />
              <span className="text-sm font-extrabold text-amber-700 tracking-wide">{credits} Credits</span>
            </div>

            <div className="hidden sm:flex items-center space-x-3 bg-white px-5 py-2.5 rounded-2xl border border-slate-200">
              {user?.picture && !pictureFailed ? (
                <img
                  src={user.picture}
                  alt={user?.name || 'User'}
                  className="w-10 h-10 rounded-full"
                  referrerPolicy="no-referrer"
                  crossOrigin="anonymous"
                  onError={handlePictureError}
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-indigo-50 flex items-center justify-center text-indigo-600 font-bold border border-indigo-100">
                  {user?.name?.[0]?.toUpperCase() || 'U'}
                </div>
              )}
              <span className="text-sm font-bold text-slate-600 max-w-[150px] truncate">
                {user?.name || user?.email || 'Authenticated User'}
              </span>
            </div>

            <button
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              className="clay-tab flex items-center space-x-2 py-3 px-5 text-sm font-bold text-rose-500 hover:text-rose-600 hover:bg-rose-50 border border-slate-200"
              title="Logout"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>

          <div className="flex items-center justify-center space-x-3">
            <img src={drishtiLogo} alt="Drishti Logo" className="h-16 w-auto object-contain" />
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-slate-800 pb-1">
              Drishti <span className="text-indigo-600">Deepfake</span>
            </h1>
          </div>
          <p className="text-slate-500 max-w-2xl mx-auto text-lg font-medium">
            Detect the fake. Protect the truth.
          </p>
        </header>

        <div className="clay-card p-3 max-w-4xl mx-auto">
          <nav className="flex items-center space-x-3 overflow-x-auto select-none p-1" aria-label="Tabs">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              const isDisabled = !!(tab as any).disabled;

              return (
                <button
                  key={tab.id}
                  onClick={() => !isDisabled && setActiveTab(tab.id as TabType)}
                  disabled={isDisabled}
                  className={`flex-1 flex min-w-[140px] items-center justify-center space-x-2 py-3.5 px-4 clay-tab ${isDisabled ? 'opacity-40 cursor-not-allowed' : isActive ? 'active' : ''}`}
                  aria-current={isActive ? 'page' : undefined}
                  title={isDisabled ? 'Coming soon' : undefined}
                >
                  <Icon size={18} className={isDisabled ? 'text-slate-400' : isActive ? 'text-white' : 'text-indigo-500'} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        <main className="clay-card p-6 md:p-10 relative overflow-hidden">
          <div className="relative z-10">
            {activeTab === 'IMAGE' ? (
              <ImageDetectorTab />
            ) : activeTab === 'DOCUMENT' ? (
              <DocumentDetectorTab credits={credits} setCredits={setCredits} />
            ) : currentTabInfo ? (
              <DetectorTab
                key={activeTab}
                acceptType={currentTabInfo.accept}
                typeLabel={currentTabInfo.id !== 'COMBINED' ? currentTabInfo.label : 'Media'}
                description={currentTabInfo.desc}
                credits={credits}
                setCredits={setCredits}
              />
            ) : null}
          </div>
        </main>

        <footer className="text-center text-slate-400 font-bold text-sm mt-12 pb-4">
           Powered by Drishti
        </footer>
      </div>
    </div>
  );
}

export default App;