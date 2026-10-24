import torch
import torch.nn as nn
import timm

class VideoDeepfakeModel(nn.Module):
    def __init__(self, sequence_length=15, lstm_hidden_size=512, lstm_layers=1, dropout=0.5):
        """
        Extract EfficientNet-B4 features per frame and classify the sequence with an LSTM.
        """
        super(VideoDeepfakeModel, self).__init__()

        self.sequence_length = sequence_length

        # Use ImageNet features without the image-classification head.
        self.feature_extractor = timm.create_model('tf_efficientnet_b4_ns', pretrained=True, num_classes=0)


        feature_dim = self.feature_extractor.num_features

        # Train the temporal head before fine-tuning the backbone.
        for param in self.feature_extractor.parameters():
            param.requires_grad = False

        self.lstm = nn.LSTM(
            input_size=feature_dim,
            hidden_size=lstm_hidden_size,
            num_layers=lstm_layers,
            batch_first=True, # Input format: (batch, seq, feature)
            dropout=dropout if lstm_layers > 1 else 0.0
        )

        self.classifier = nn.Sequential(
            nn.Linear(lstm_hidden_size, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 1)
            # BCEWithLogitsLoss applies sigmoid during training.
        )

    def forward(self, x):
        """
        Input: Tensor of shape (Batch_Size, Sequence_Length, Channels(3), Height(299), Width(299))
        Output: Tensor of shape (Batch_Size, 1) containing unnormalized FAKE logits.
        """
        batch_size, seq_length, c, h, w = x.size()

        # Run all frames through the CNN, then restore the sequence dimension.
        x = x.view(batch_size * seq_length, c, h, w)


        features = self.feature_extractor(x)


        features = features.view(batch_size, seq_length, -1)

        # lstm_out shape: (Batch, Seq_Len, lstm_hidden)
        lstm_out, (hidden_state, cell_state) = self.lstm(features)

        # Classify from the final LSTM step.
        last_hidden_output = lstm_out[:, -1, :] # Shape: (Batch, lstm_hidden)

        out = self.classifier(last_hidden_output) # Shape: (Batch, 1)

        return out

    def unfreeze_backbone(self, num_layers=5):
        """
        Call this to unfreeze the top layers of the backbone during fine-tuning (Stage 2).
        """
        for count, child in enumerate(reversed(list(self.feature_extractor.children()))):
            if count < num_layers:
                for param in child.parameters():
                    param.requires_grad = True

if __name__ == "__main__":
    # Check the forward-pass shape with synthetic input.
    print("Testing Model Compilation & Forward Pass...")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = VideoDeepfakeModel().to(device)

    # Dummy Input mimicking our Video Data Tensor: 2 videos, 15 frames each, 3 channel (RGB), 299x299 resolution
    print("Creating dummy tensor shape: (Batch=2, Seq=15, C=3, H=299, W=299)")
    dummy_input = torch.randn(2, 15, 3, 299, 299).to(device)

    output = model(dummy_input)
    print(f"Model Forward successful! Final Output Shape: {output.shape} (Outputs: {output.detach().cpu().numpy().flatten()})")
    print(f"To represent FAKE probabilities for the 2 videos.")
