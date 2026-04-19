import React, { useState } from 'react';

const EditPortfolioModal = ({ isOpen, onClose, portfolio, onSave }) => {
    const [name, setName] = useState(portfolio.name);
    const [assets, setAssets] = useState(portfolio.assets);
    const [allocations, setAllocations] = useState(portfolio.allocations);
    const [rebalanceMode, setRebalanceMode] = useState(portfolio.rebalanceMode);
    const [threshold, setThreshold] = useState(portfolio.threshold);

    const handleSave = () => {
        const updatedPortfolio = {
            name,
            assets,
            allocations,
            rebalanceMode,
            threshold,
        };
        onSave(updatedPortfolio);
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="modal">
            <h2>Edit Portfolio</h2>
            <label>
                Portfolio Name:
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
                Assets:
                <textarea value={assets} onChange={(e) => setAssets(e.target.value)} />
            </label>
            <label>
                Allocations:
                <textarea value={allocations} onChange={(e) => setAllocations(e.target.value)} />
            </label>
            <label>
                Rebalance Mode:
                <select value={rebalanceMode} onChange={(e) => setRebalanceMode(e.target.value)}>
                    <option value="manual">Manual</option>
                    <option value="automatic">Automatic</option>
                </select>
            </label>
            <label>
                Threshold:
                <input type="number" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </label>
            <button onClick={handleSave}>Save</button>
            <button onClick={onClose}>Cancel</button>
        </div>
    );
};

export default EditPortfolioModal;