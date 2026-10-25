-- Run AFTER training has passed holdout validation and --write-weights.
-- The fixture uses dates in 2081. Set @AsOf after the synthetic history;
-- omitting it would use the current date and score an empty history.
EXEC dbo.AssignBestAgents
    @CustomerName = 'Synthetic Customer',
    @CommunicationMethod = 'Phone Call',
    @LeadSource = 'Organic',
    @Destination = 'Mars',
    @LaunchLocation = 'Earth Orbital Station',
    @Requirements = 'Luxury Dome Stay',
    @AsOf = '2081-04-11T00:00:00';
