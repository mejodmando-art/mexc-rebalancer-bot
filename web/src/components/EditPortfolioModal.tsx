import React, { useState } from 'react';
import './EditPortfolioModal.css';

const EditPortfolioModal = ({ isOpen, onClose }) => {
    const [botName, setBotName] = useState('');
    const [totalUSDT, setTotalUSDT] = useState(0);
    const [assets, setAssets] = useState([{ symbol: '', allocation: 0 }]);
    const [rebalanceMode, setRebalanceMode] = useState('');
    const [deviationThreshold, setDeviationThreshold] = useState(0);
    const [stopLoss, setStopLoss] = useState(0);
    const [takeProfit, setTakeProfit] = useState(0);
    const [sellAtTermination, setSellAtTermination] = useState(false);
    const [paperTrading, setPaperTrading] = useState(false);

    const handleAssetChange = (index, field, value) => {
        const newAssets = [...assets];
        newAssets[index][field] = value;
        setAssets(newAssets);
    };

    const addAsset = () => {
        setAssets([...assets, { symbol: '', allocation: 0 }]);
    };

    const handleSubmit = () => {
        // Handle form submission
        // TODO: Add form submission logic
        console.log('Form submitted:', { botName, totalUSDT, assets, rebalanceMode, deviationThreshold, stopLoss, takeProfit, sellAtTermination, paperTrading });
        onClose();
    };

    return (
        <div className={`modal ${isOpen ? 'is-open' : ''}`}>
            <div className="modal-content">
                <h2>Edit Portfolio Settings</h2>
                <form>
                    <div>
                        <label>Bot Name:</label>
                        <input type="text" value={botName} onChange={(e) => setBotName(e.target.value)} />
                    </div>
                    <div>
                        <label>Total USDT:</label>
                        <input type="number" value={totalUSDT} onChange={(e) => setTotalUSDT(Number(e.target.value))} />
                    </div>
                    <div>
                        <label>Assets Management:</label>
                        {assets.map((asset, index) => (
                            <div key={index} className="asset-group">
                                <input type="text" placeholder="Symbol" value={asset.symbol} onChange={(e) => handleAssetChange(index, 'symbol', e.target.value)} />
                                <input type="number" placeholder="Allocation (%)" value={asset.allocation} onChange={(e) => handleAssetChange(index, 'allocation', Number(e.target.value))} />
                                <button type="button" onClick={() => addAsset()}>Add Asset</button>
                            </div>
                        ))}
                    </div>
                    <div>
                        <label>Rebalance Mode:</label>
                        <select value={rebalanceMode} onChange={(e) => setRebalanceMode(e.target.value)}>
                            <option value="">Select</option>
                            <option value="manual">Manual</option>
                            <option value="automatic">Automatic</option>
                        </select>
                    </div>
                    <div>
                        <label>Deviation Threshold:</label>
                        <input type="number" value={deviationThreshold} onChange={(e) => setDeviationThreshold(Number(e.target.value))} />
                    </div>
                    <div>
                        <label>Stop Loss (%):</label>
                        <input type="number" value={stopLoss} onChange={(e) => setStopLoss(Number(e.target.value))} />
                    </div>
                    <div>
                        <label>Take Profit (%):</label>
                        <input type="number" value={takeProfit} onChange={(e) => setTakeProfit(Number(e.target.value))} />
                    </div>
                    <div>
                        <label>
                            <input type="checkbox" checked={sellAtTermination} onChange={(e) => setSellAtTermination(e.target.checked)} />
                            Sell at Termination
                        </label>
                    </div>
                    <div>
                        <label>
                            <input type="checkbox" checked={paperTrading} onChange={(e) => setPaperTrading(e.target.checked)} />
                            Paper Trading
                        </label>
                    </div>
                    <button type="button" onClick={handleSubmit}>Save</button>
                    <button type="button" onClick={onClose}>Cancel</button>
                </form>
            </div>
        </div>
    );
};

export default EditPortfolioModal;