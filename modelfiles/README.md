# ProcessAuth — Custom Model Training

These Modelfiles permanently embed expert humanizer instructions into local Ollama models.
Run the commands below **once** to register them. They'll then appear in the ProcessAuth dropdown.

## Build the Custom Models

Open a PowerShell terminal in this folder and run:

```powershell
# Build the llama3.2 humanizer
ollama create processauth-llama -f llama3.2-humanizer.Modelfile

# Build the gemma3 humanizer
ollama create processauth-gemma -f gemma3-humanizer.Modelfile
```

## Verify

```powershell
ollama list
# You should see processauth-llama and processauth-gemma in the list
```

Then restart ProcessAuth — both models will appear in the Model dropdown.

## Re-training

To update the system prompt, edit the `SYSTEM` block in the Modelfile, then re-run the `ollama create` command above. It will overwrite the old version.
